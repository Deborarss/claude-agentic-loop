"""O agentic loop "na mão", do jeito que a Messages API funciona.

Esta é a versão didática: mostra exatamente o que acontece por baixo de
qualquer framework de agentes.

    ┌──────────────► before_iteration() ── para? ─► AgentResult
    │                      │
    │           client.messages.create(...)
    │                      │
    │            stop_reason == "tool_use"? ── não ─► AgentResult
    │                      │ sim
    │         executa cada tool (com guardas)
    │                      │
    └──── devolve os tool_result como mensagem "user"

O `client` é injetado: nos testes usamos um cliente falso (sem custo) e,
com créditos de API, basta passar `anthropic.Anthropic()`.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from .termination import AgentResult, Limits, StopReason, TerminationGuard, map_model_stop_reason
from .tools import anthropic_tool_definitions, execute_tool

DEFAULT_MODEL = "claude-haiku-4-5"
SYSTEM_PROMPT = (
    "Você é um assistente objetivo. Use as tools disponíveis quando precisar de "
    "cálculos exatos, da hora atual ou de dados de chamados. Responda em português."
)


class MessagesClient(Protocol):
    """O pedaço do SDK `anthropic` que o loop usa: `client.messages.create(...)`."""

    messages: Any


def _block_to_dict(block: Any) -> dict[str, Any]:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": block.type}


def run_raw_loop(
    client: MessagesClient,
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    limits: Limits | None = None,
    max_tokens: int = 1024,
    clock: Callable[[], float] = time.monotonic,
) -> AgentResult:
    guard = TerminationGuard(limits, clock)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    final_text = ""

    def finish(reason: StopReason) -> AgentResult:
        return AgentResult(final_text, reason, guard.iterations, guard.total_tokens, messages)

    while True:
        if reason := guard.before_iteration():
            return finish(reason)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                tools=anthropic_tool_definitions(),
                messages=messages,
            )
        except Exception as exc:  # erro de rede/API: para, não tenta de novo para sempre
            final_text = f"Erro ao chamar o modelo: {exc}"
            return finish(StopReason.ERROR)

        blocks = [_block_to_dict(b) for b in response.content]
        messages.append({"role": "assistant", "content": blocks})
        text = "\n".join(b["text"] for b in blocks if b["type"] == "text").strip()
        if text:
            final_text = text

        if reason := guard.record_usage(response.usage.input_tokens, response.usage.output_tokens):
            return finish(reason)

        # end_turn, max_tokens, refusal... -> para. tool_use -> continua.
        if (reason := map_model_stop_reason(response.stop_reason)) is not None:
            return finish(reason)

        tool_results: list[dict[str, Any]] = []
        for block in blocks:
            if block["type"] != "tool_use":
                continue
            if reason := guard.check_tool_call(block["name"], block["input"]):
                return finish(reason)
            output, is_error = execute_tool(block["name"], block["input"])
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": output, "is_error": is_error}
            )
            if reason := guard.record_tool_result(is_error):
                return finish(reason)

        # Todo tool_use precisa de um tool_result correspondente na próxima mensagem "user".
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
