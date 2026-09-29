from fake_client import FakeClient, response, text, tool_use

from agent_loop.raw_loop import run_raw_loop
from agent_loop.termination import Limits, StopReason


def test_caminho_feliz_com_duas_tools():
    client = FakeClient(
        [
            response(
                text("Vou calcular e ver a hora."),
                tool_use("calculator", {"expression": "17*23"}, id="t1"),
                tool_use("get_current_time", {"timezone": "UTC"}, id="t2"),
                stop_reason="tool_use",
            ),
            response(text("17*23 = 391.")),
        ]
    )
    result = run_raw_loop(client, "Quanto é 17*23 e que horas são?")

    assert result.ok
    assert result.stop_reason is StopReason.COMPLETED
    assert result.final_text == "17*23 = 391."
    assert result.iterations == 2
    assert result.total_tokens == 30

    # A 2ª chamada precisa conter os tool_result, um para cada tool_use.
    tool_results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in tool_results] == ["t1", "t2"]
    assert tool_results[0]["content"] == "391"
    assert tool_results[0]["is_error"] is False


def test_tools_sao_enviadas_para_a_api():
    client = FakeClient([response(text("oi"))])
    run_raw_loop(client, "oi")
    assert {t["name"] for t in client.calls[0]["tools"]} == {"calculator", "get_current_time", "lookup_ticket"}


def test_erro_de_tool_volta_para_o_modelo_e_ele_se_recupera():
    client = FakeClient(
        [
            response(tool_use("lookup_ticket", {"ticket_id": "INC9999"}), stop_reason="tool_use"),
            response(text("Esse chamado não existe.")),
        ]
    )
    result = run_raw_loop(client, "Status do INC9999?")
    assert result.ok
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_max_iterations_para_modelo_que_nunca_termina():
    # O modelo pede uma tool diferente a cada volta, para sempre.
    responses = [
        response(tool_use("calculator", {"expression": f"{i}+1"}, id=f"t{i}"), stop_reason="tool_use")
        for i in range(100)
    ]
    client = FakeClient(responses)
    result = run_raw_loop(client, "loop", limits=Limits(max_iterations=5))
    assert result.stop_reason is StopReason.MAX_ITERATIONS
    assert len(client.calls) == 5


def test_chamada_repetida_detecta_loop():
    client = FakeClient(
        [response(tool_use("calculator", {"expression": "1+1"}), stop_reason="tool_use")], repeat_last=True
    )
    result = run_raw_loop(client, "loop", limits=Limits(max_repeated_calls=3, max_iterations=50))
    assert result.stop_reason is StopReason.REPEATED_TOOL_CALL
    assert len(client.calls) == 3


def test_muitos_erros_de_tool_seguidos():
    responses = [
        response(tool_use("lookup_ticket", {"ticket_id": f"X{i}"}, id=f"t{i}"), stop_reason="tool_use")
        for i in range(10)
    ]
    result = run_raw_loop(FakeClient(responses), "x", limits=Limits(max_consecutive_errors=3))
    assert result.stop_reason is StopReason.TOO_MANY_TOOL_ERRORS
    assert result.iterations == 3


def test_orcamento_de_tokens():
    client = FakeClient(
        [response(tool_use("calculator", {"expression": "1+1"}), stop_reason="tool_use", input_tokens=600)],
        repeat_last=True,
    )
    result = run_raw_loop(client, "x", limits=Limits(max_total_tokens=1000))
    assert result.stop_reason is StopReason.TOKEN_BUDGET
    assert result.iterations == 2


def test_timeout():
    clock_values = iter([0.0, 0.0, 999.0])  # início, 1ª volta, 2ª volta
    client = FakeClient(
        [
            response(tool_use("calculator", {"expression": "1+1"}), stop_reason="tool_use"),
            response(text("nunca chega aqui")),
        ]
    )
    result = run_raw_loop(client, "x", limits=Limits(timeout_seconds=60), clock=lambda: next(clock_values))
    assert result.stop_reason is StopReason.TIMEOUT
    assert len(client.calls) == 1


def test_max_tokens_resposta_cortada():
    result = run_raw_loop(FakeClient([response(text("resposta pela met"), stop_reason="max_tokens")]), "x")
    assert result.stop_reason is StopReason.MAX_TOKENS
    assert not result.ok
    assert result.final_text == "resposta pela met"


def test_refusal():
    result = run_raw_loop(FakeClient([response(stop_reason="refusal")]), "x")
    assert result.stop_reason is StopReason.REFUSAL


def test_erro_da_api_nao_derruba_o_programa():
    result = run_raw_loop(FakeClient([ConnectionError("sem rede")]), "x")
    assert result.stop_reason is StopReason.ERROR
    assert "sem rede" in result.final_text
