"""Cliente falso que imita `anthropic.Anthropic()`, com respostas roteirizadas.

Permite testar cada caminho do loop (inclusive os de falha) sem chamar a API.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def tool_use(name: str, tool_input: dict[str, Any], id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=tool_input)


def response(*content: SimpleNamespace, stop_reason: str = "end_turn", input_tokens: int = 10, output_tokens: int = 5):
    return SimpleNamespace(
        content=list(content),
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class FakeClient:
    """Devolve as respostas na ordem dada. Se `repeat_last`, repete a última para sempre."""

    def __init__(self, responses: list[Any], repeat_last: bool = False):
        self._responses = list(responses)
        self._repeat_last = repeat_last
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # permite `client.messages.create(...)`

    def create(self, **kwargs: Any) -> Any:
        # Guarda uma cópia: o loop continua alterando a lista de mensagens depois.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if len(self._responses) > 1 or not self._repeat_last:
            item = self._responses.pop(0)
        else:
            item = self._responses[0]
        if isinstance(item, Exception):
            raise item
        return item
