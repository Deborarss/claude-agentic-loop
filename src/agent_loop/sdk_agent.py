"""O mesmo agente, agora usando o Claude Agent SDK.

Aqui o loop (chamar o modelo -> executar tools -> devolver resultados) é feito
pelo SDK. Nosso trabalho é *configurar* as guardas de parada:

- `max_turns`               -> limite de voltas (o SDK para sozinho)
- `max_budget_usd`          -> limite de custo estimado
- hook `PreToolUse`         -> bloqueia chamadas repetidas e para após erros seguidos
- `asyncio.timeout`         -> tempo máximo de relógio
- `tools=[]`                -> desliga as tools embutidas (arquivos, shell, web)

O SDK usa o Claude Code instalado na máquina e a autenticação configurada nele.
"""

from __future__ import annotations

import asyncio
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .raw_loop import SYSTEM_PROMPT
from .termination import AgentResult, Limits, StopReason, TerminationGuard
from .tools import SDK_SERVER_NAME, build_sdk_server, sdk_tool_names

RESULT_SUBTYPES = {
    "success": StopReason.COMPLETED,
    "error_max_turns": StopReason.MAX_ITERATIONS,
    "error_max_budget_usd": StopReason.TOKEN_BUDGET,
}


def total_tokens(usage: dict[str, Any] | None) -> int:
    """Soma todos os tokens de entrada e saída, incluindo os de cache.

    Com prompt caching, a maior parte da entrada aparece em
    `cache_creation_input_tokens` / `cache_read_input_tokens`, não em `input_tokens`.
    """
    usage = usage or {}
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    return sum(int(usage.get(k) or 0) for k in keys)


def _deny(reason: StopReason, message: str) -> dict[str, Any]:
    """Resposta de hook que bloqueia a tool E encerra o agente."""
    return {
        "continue_": False,
        "stopReason": f"Guarda de parada: {reason.value}",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        },
    }


async def run_sdk_agent(
    prompt: str,
    *,
    limits: Limits | None = None,
    model: str | None = None,
    max_budget_usd: float | None = 0.50,
) -> AgentResult:
    guard = TerminationGuard(limits)
    limits = guard.limits
    stop_override: StopReason | None = None
    pending_stop: StopReason | None = None

    def on_tool_result(_name: str, is_error: bool) -> None:
        nonlocal pending_stop
        pending_stop = pending_stop or guard.record_tool_result(is_error)

    async def pre_tool_use(input_data: dict[str, Any], _tool_use_id: str | None, _ctx: Any) -> dict[str, Any]:
        nonlocal stop_override
        reason = pending_stop or guard.check_tool_call(input_data["tool_name"], input_data["tool_input"])
        if reason:
            stop_override = reason
            return _deny(reason, f"Execução interrompida pela guarda {reason.value}.")
        return {}

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=model,
        tools=[],
        mcp_servers={SDK_SERVER_NAME: build_sdk_server(on_tool_result)},
        # Só o nosso MCP server: ignora servidores MCP de outras fontes (conta,
        # plugins, .mcp.json), cujas tools ocupariam contexto em toda chamada.
        strict_mcp_config=True,
        skills=[],
        allowed_tools=sdk_tool_names(),
        permission_mode="dontAsk",
        setting_sources=[],  # não carrega CLAUDE.md nem settings do usuário
        max_turns=limits.max_iterations,
        max_budget_usd=max_budget_usd,
        hooks={"PreToolUse": [HookMatcher(matcher=f"^mcp__{SDK_SERVER_NAME}__", hooks=[pre_tool_use])]},
    )

    final_text = ""
    transcript: list[dict[str, Any]] = []
    result: ResultMessage | None = None

    try:
        async with asyncio.timeout(limits.timeout_seconds):
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            final_text = block.text.strip()
                            transcript.append({"type": "text", "text": block.text})
                        elif isinstance(block, ToolUseBlock):
                            transcript.append({"type": "tool_use", "name": block.name, "input": block.input})
                elif isinstance(message, ResultMessage):
                    result = message
    except TimeoutError:
        return AgentResult(final_text, StopReason.TIMEOUT, guard.iterations, 0, transcript)
    except ResultError as exc:
        # Em execuções que terminam com erro (ex.: max_turns), o SDK primeiro entrega
        # o ResultMessage e depois levanta ResultError. O resultado já diz o motivo.
        if result is None:
            subtype = (exc.data or {}).get("subtype", "")
            reason = stop_override or RESULT_SUBTYPES.get(subtype, StopReason.ERROR)
            return AgentResult(final_text or str(exc), reason, 0, 0, transcript)
    except Exception as exc:
        return AgentResult(f"Erro no Agent SDK: {exc}", StopReason.ERROR, guard.iterations, 0, transcript)

    if result is None:
        return AgentResult(final_text, stop_override or StopReason.ERROR, 0, 0, transcript)

    tokens = total_tokens(result.usage)
    reason = stop_override or RESULT_SUBTYPES.get(result.subtype, StopReason.ERROR)
    if reason is StopReason.COMPLETED and result.result:
        final_text = result.result.strip()
    return AgentResult(final_text, reason, result.num_turns, tokens, transcript)
