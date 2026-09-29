import pytest

from agent_loop.termination import Limits, StopReason, TerminationGuard, map_model_stop_reason


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_max_iterations():
    guard = TerminationGuard(Limits(max_iterations=2))
    assert guard.before_iteration() is None
    assert guard.before_iteration() is None
    assert guard.before_iteration() is StopReason.MAX_ITERATIONS


def test_timeout():
    clock = FakeClock()
    guard = TerminationGuard(Limits(timeout_seconds=30), clock=clock)
    assert guard.before_iteration() is None
    clock.now = 31
    assert guard.before_iteration() is StopReason.TIMEOUT


def test_orcamento_de_tokens():
    guard = TerminationGuard(Limits(max_total_tokens=100))
    assert guard.record_usage(40, 10) is None
    assert guard.record_usage(40, 10) is StopReason.TOKEN_BUDGET
    assert guard.total_tokens == 100


def test_chamada_repetida():
    guard = TerminationGuard(Limits(max_repeated_calls=3))
    assert guard.check_tool_call("calculator", {"expression": "1+1"}) is None
    assert guard.check_tool_call("calculator", {"expression": "2+2"}) is None  # argumento diferente
    assert guard.check_tool_call("calculator", {"expression": "1+1"}) is None
    assert guard.check_tool_call("calculator", {"expression": "1+1"}) is StopReason.REPEATED_TOOL_CALL


def test_chamada_repetida_ignora_ordem_das_chaves():
    guard = TerminationGuard(Limits(max_repeated_calls=2))
    assert guard.check_tool_call("t", {"a": 1, "b": 2}) is None
    assert guard.check_tool_call("t", {"b": 2, "a": 1}) is StopReason.REPEATED_TOOL_CALL


def test_erros_consecutivos_zeram_com_sucesso():
    guard = TerminationGuard(Limits(max_consecutive_errors=2))
    assert guard.record_tool_result(is_error=True) is None
    assert guard.record_tool_result(is_error=False) is None  # sucesso zera o contador
    assert guard.record_tool_result(is_error=True) is None
    assert guard.record_tool_result(is_error=True) is StopReason.TOO_MANY_TOOL_ERRORS


@pytest.mark.parametrize(
    ("api_stop", "expected"),
    [
        ("tool_use", None),
        ("pause_turn", None),
        ("end_turn", StopReason.COMPLETED),
        ("stop_sequence", StopReason.COMPLETED),
        ("max_tokens", StopReason.MAX_TOKENS),
        ("refusal", StopReason.REFUSAL),
        ("algo_novo", StopReason.ERROR),
        (None, StopReason.ERROR),
    ],
)
def test_map_model_stop_reason(api_stop, expected):
    assert map_model_stop_reason(api_stop) is expected
