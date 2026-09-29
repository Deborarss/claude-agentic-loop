"""Guardas de parada segura (safe termination).

Um agentic loop é um `while` que deixa o *modelo* decidir quando parar.
Isso é poderoso, mas perigoso: o modelo pode repetir a mesma tool para sempre,
estourar o orçamento ou ficar travado. As guardas abaixo garantem que o loop
SEMPRE termina, e sempre com um motivo explícito.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class StopReason(str, Enum):
    COMPLETED = "completed"                    # o modelo terminou (end_turn)
    MAX_ITERATIONS = "max_iterations"          # muitas voltas no loop
    TOKEN_BUDGET = "token_budget"              # gastou tokens demais
    TIMEOUT = "timeout"                        # passou do tempo de relógio
    REPEATED_TOOL_CALL = "repeated_tool_call"  # mesma tool + mesmos argumentos em loop
    TOO_MANY_TOOL_ERRORS = "too_many_tool_errors"
    MAX_TOKENS = "max_tokens"                  # resposta cortada pelo limite de saída
    REFUSAL = "refusal"                        # o modelo se recusou a continuar
    ERROR = "error"                            # erro inesperado (API, rede...)


@dataclass(frozen=True)
class Limits:
    max_iterations: int = 10
    max_total_tokens: int = 50_000
    timeout_seconds: float = 120.0
    max_repeated_calls: int = 3       # a N-ésima chamada idêntica para o loop
    max_consecutive_errors: int = 3


@dataclass
class AgentResult:
    final_text: str
    stop_reason: StopReason
    iterations: int
    total_tokens: int = 0
    transcript: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.stop_reason is StopReason.COMPLETED


def map_model_stop_reason(stop_reason: str | None) -> StopReason | None:
    """Traduz o `stop_reason` da Messages API.

    Devolve `None` quando o loop deve continuar (o modelo pediu uma tool).
    """
    match stop_reason:
        case "tool_use" | "pause_turn":
            return None
        case "end_turn" | "stop_sequence":
            return StopReason.COMPLETED
        case "max_tokens":
            return StopReason.MAX_TOKENS
        case "refusal":
            return StopReason.REFUSAL
        case _:
            return StopReason.ERROR


def call_signature(name: str, tool_input: dict[str, Any]) -> str:
    """Identidade de uma chamada: nome + argumentos normalizados."""
    return f"{name}:{json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}"


class TerminationGuard:
    """Guarda com estado: cada método devolve um `StopReason` se o loop deve parar, ou `None`."""

    def __init__(self, limits: Limits | None = None, clock: Callable[[], float] = time.monotonic):
        self.limits = limits or Limits()
        self._clock = clock
        self._started_at = clock()
        self.iterations = 0
        self.total_tokens = 0
        self._call_counts: Counter[str] = Counter()
        self._consecutive_errors = 0

    def before_iteration(self) -> StopReason | None:
        """Chamado no início de cada volta, antes de falar com o modelo."""
        if self.iterations >= self.limits.max_iterations:
            return StopReason.MAX_ITERATIONS
        if self.elapsed() >= self.limits.timeout_seconds:
            return StopReason.TIMEOUT
        self.iterations += 1
        return None

    def record_usage(self, input_tokens: int, output_tokens: int) -> StopReason | None:
        self.total_tokens += input_tokens + output_tokens
        if self.total_tokens >= self.limits.max_total_tokens:
            return StopReason.TOKEN_BUDGET
        return None

    def check_tool_call(self, name: str, tool_input: dict[str, Any]) -> StopReason | None:
        sig = call_signature(name, tool_input)
        self._call_counts[sig] += 1
        if self._call_counts[sig] >= self.limits.max_repeated_calls:
            return StopReason.REPEATED_TOOL_CALL
        return None

    def record_tool_result(self, is_error: bool) -> StopReason | None:
        self._consecutive_errors = self._consecutive_errors + 1 if is_error else 0
        if self._consecutive_errors >= self.limits.max_consecutive_errors:
            return StopReason.TOO_MANY_TOOL_ERRORS
        return None

    def elapsed(self) -> float:
        return self._clock() - self._started_at
