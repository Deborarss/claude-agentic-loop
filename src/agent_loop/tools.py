"""Tools que o agente pode usar.

Cada tool é definida uma única vez (nome, descrição, JSON Schema e função Python)
e reaproveitada pelas duas implementações do loop:
- `raw_loop.py` usa `anthropic_tool_definitions()` (formato da Messages API);
- `sdk_agent.py` usa `build_sdk_server()` (MCP server in-process do Agent SDK).

Todas são seguras de propósito: sem acesso a arquivos, shell ou rede.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ToolError(Exception):
    """Erro esperado de uma tool. A mensagem volta para o Claude como `is_error`."""


# --- calculator -------------------------------------------------------------

_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Callable[[Any], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ToolError("Expoente grande demais (máximo 100).")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ToolError(f"Expressão não suportada: {ast.dump(node)[:60]}")


def calculator(expression: str) -> str:
    """Avalia uma expressão aritmética sem usar `eval()` (que executaria qualquer código)."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
    except ToolError:
        raise
    except ZeroDivisionError:
        raise ToolError("Divisão por zero.")
    except SyntaxError:
        raise ToolError(f"Expressão inválida: {expression!r}")
    return str(result)


# --- get_current_time -------------------------------------------------------


def get_current_time(timezone: str = "America/Sao_Paulo") -> str:
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        raise ToolError(f"Fuso horário desconhecido: {timezone!r}")
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


# --- lookup_ticket ----------------------------------------------------------

# Base FICTÍCIA de chamados, só para estudo.
FAKE_TICKETS: dict[str, dict[str, str]] = {
    "INC0001": {"sistema": "Salesforce", "status": "Aberto", "resumo": "Usuário sem acesso ao relatório de vendas"},
    "INC0002": {"sistema": "CDP", "status": "Em andamento", "resumo": "Carga diária de clientes atrasada"},
    "REQ0003": {"sistema": "Salesforce", "status": "Resolvido", "resumo": "Criação de novo perfil de acesso"},
}


def lookup_ticket(ticket_id: str) -> str:
    ticket = FAKE_TICKETS.get(ticket_id.strip().upper())
    if ticket is None:
        raise ToolError(f"Chamado {ticket_id!r} não encontrado.")
    return f"{ticket_id.upper()} | {ticket['sistema']} | {ticket['status']} | {ticket['resumo']}"


# --- registro ---------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., str]


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="calculator",
            description="Avalia uma expressão aritmética (+, -, *, /, //, %, **). Ex.: '17*23'.",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Expressão aritmética"}},
                "required": ["expression"],
            },
            fn=calculator,
        ),
        ToolSpec(
            name="get_current_time",
            description="Retorna data e hora atuais em um fuso horário IANA (padrão: America/Sao_Paulo).",
            input_schema={
                "type": "object",
                "properties": {"timezone": {"type": "string", "description": "Ex.: America/Sao_Paulo"}},
            },
            fn=get_current_time,
        ),
        ToolSpec(
            name="lookup_ticket",
            description="Consulta um chamado de suporte (base fictícia) pelo ID, ex.: INC0001.",
            input_schema={
                "type": "object",
                "properties": {"ticket_id": {"type": "string", "description": "ID do chamado"}},
                "required": ["ticket_id"],
            },
            fn=lookup_ticket,
        ),
    ]
}


def execute_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
    """Executa uma tool e devolve `(texto, is_error)`.

    Nunca levanta exceção: qualquer falha vira um resultado com `is_error=True`,
    assim o Claude pode ler o erro e tentar outra abordagem.
    """
    spec = TOOLS.get(name)
    if spec is None:
        return f"Tool desconhecida: {name!r}", True
    try:
        return spec.fn(**tool_input), False
    except ToolError as exc:
        return str(exc), True
    except TypeError as exc:  # argumentos errados
        return f"Argumentos inválidos para {name}: {exc}", True


def anthropic_tool_definitions() -> list[dict[str, Any]]:
    """Tools no formato do parâmetro `tools` da Messages API."""
    return [
        {"name": s.name, "description": s.description, "input_schema": s.input_schema}
        for s in TOOLS.values()
    ]


SDK_SERVER_NAME = "lab"


def sdk_tool_names() -> list[str]:
    """Nomes que o Agent SDK usa para as tools de um MCP server: `mcp__<server>__<tool>`."""
    return [f"mcp__{SDK_SERVER_NAME}__{name}" for name in TOOLS]


def build_sdk_server(on_result: Callable[[str, bool], None] | None = None):
    """Empacota as tools como um MCP server in-process do Agent SDK.

    `on_result(nome, is_error)` é chamado após cada execução (usado pelas guardas).
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    def wrap(spec: ToolSpec):
        @tool(spec.name, spec.description, spec.input_schema)
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            text, is_error = execute_tool(spec.name, args)
            if on_result:
                on_result(spec.name, is_error)
            return {"content": [{"type": "text", "text": text}], "is_error": is_error}

        return handler

    return create_sdk_mcp_server(name=SDK_SERVER_NAME, tools=[wrap(s) for s in TOOLS.values()])
