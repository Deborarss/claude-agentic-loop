"""Testes do sdk_agent com um `query` falso: não inicia o Claude Code nem gasta cota."""

import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, ResultError, ResultMessage, TextBlock, ToolUseBlock

from agent_loop import sdk_agent
from agent_loop.termination import Limits, StopReason


def result_message(subtype="success", result="ok", num_turns=2, is_error=False):
    return ResultMessage(
        subtype=subtype,
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=num_turns,
        session_id="s1",
        result=result,
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def fake_query(script):
    """Cria um `query` falso. `script(options)` é um async generator de mensagens."""

    def _query(*, prompt, options):
        return script(options)

    return _query


async def call_pre_tool_use(options, name, tool_input):
    hook = options.hooks["PreToolUse"][0].hooks[0]
    return await hook({"tool_name": name, "tool_input": tool_input}, "toolu_1", None)


async def test_sucesso(monkeypatch):
    async def script(options):
        yield AssistantMessage(content=[ToolUseBlock(id="t1", name="mcp__lab__calculator", input={"expression": "1+1"})], model="m")
        yield AssistantMessage(content=[TextBlock(text="2")], model="m")
        yield result_message(result="1+1 = 2")

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("1+1?")

    assert result.stop_reason is StopReason.COMPLETED
    assert result.final_text == "1+1 = 2"
    assert result.iterations == 2
    assert result.total_tokens == 15
    assert result.transcript[0]["type"] == "tool_use"


async def test_opcoes_de_seguranca(monkeypatch):
    captured = {}

    async def script(options):
        captured["options"] = options
        yield result_message()

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    await sdk_agent.run_sdk_agent("x", limits=Limits(max_iterations=4))

    options = captured["options"]
    assert options.tools == []  # sem tools embutidas (arquivos, shell, web)
    assert options.max_turns == 4
    assert options.permission_mode == "dontAsk"
    assert all(t.startswith("mcp__lab__") for t in options.allowed_tools)


async def test_max_turns_vem_como_result_error(monkeypatch):
    # Comportamento real do SDK: entrega o ResultMessage e DEPOIS levanta ResultError.
    async def script(options):
        yield result_message(subtype="error_max_turns", result=None, num_turns=1, is_error=True)
        raise ResultError("Reached maximum number of turns (1)", data={"subtype": "error_max_turns"})

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("x")
    assert result.stop_reason is StopReason.MAX_ITERATIONS
    assert result.iterations == 1


async def test_result_error_sem_result_message(monkeypatch):
    async def script(options):
        raise ResultError("budget", data={"subtype": "error_max_budget_usd"})
        yield  # pragma: no cover  (transforma a função em generator)

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("x")
    assert result.stop_reason is StopReason.TOKEN_BUDGET


async def test_hook_bloqueia_chamada_repetida(monkeypatch):
    decisions = []

    async def script(options):
        for _ in range(3):
            decisions.append(await call_pre_tool_use(options, "mcp__lab__calculator", {"expression": "1+1"}))
        yield result_message()

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("x", limits=Limits(max_repeated_calls=3))

    assert decisions[0] == {} and decisions[1] == {}
    assert decisions[2]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decisions[2]["continue_"] is False
    assert result.stop_reason is StopReason.REPEATED_TOOL_CALL


async def test_hook_para_apos_erros_seguidos(monkeypatch):
    decisions = []
    captured = {}

    def fake_build_sdk_server(on_result):
        captured["on_result"] = on_result  # o que as tools chamam após executar
        return {"type": "sdk", "name": "lab"}

    async def script(options):
        for i in range(3):
            decisions.append(await call_pre_tool_use(options, "mcp__lab__lookup_ticket", {"ticket_id": f"X{i}"}))
            captured["on_result"]("lookup_ticket", True)  # a tool falhou
        decisions.append(await call_pre_tool_use(options, "mcp__lab__lookup_ticket", {"ticket_id": "X9"}))
        yield result_message()

    monkeypatch.setattr(sdk_agent, "build_sdk_server", fake_build_sdk_server)
    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("x", limits=Limits(max_consecutive_errors=3))

    assert decisions[-1]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert result.stop_reason is StopReason.TOO_MANY_TOOL_ERRORS


async def test_timeout(monkeypatch):
    async def script(options):
        await asyncio.sleep(5)
        yield result_message()

    monkeypatch.setattr(sdk_agent, "query", fake_query(script))
    result = await sdk_agent.run_sdk_agent("x", limits=Limits(timeout_seconds=0.05))
    assert result.stop_reason is StopReason.TIMEOUT


@pytest.fixture(autouse=True)
def _sem_claude_code_real(monkeypatch):
    """Garante que nenhum teste chame o Claude Code de verdade por engano."""

    def _boom(**_):
        raise AssertionError("query real chamado no teste")

    monkeypatch.setattr(sdk_agent, "query", _boom)
