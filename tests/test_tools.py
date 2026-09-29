import pytest

from agent_loop.tools import (
    TOOLS,
    ToolError,
    anthropic_tool_definitions,
    calculator,
    execute_tool,
    get_current_time,
    lookup_ticket,
    sdk_tool_names,
)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("17*23", "391"), ("2 + 3 * 4", "14"), ("(2+3)*4", "20"), ("-5 + 2", "-3"), ("10 / 4", "2.5"), ("2**10", "1024")],
)
def test_calculator(expr, expected):
    assert calculator(expr) == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "a + 1", "1 +", "2**1000"])
def test_calculator_rejeita_codigo_e_expressoes_invalidas(expr):
    with pytest.raises(ToolError):
        calculator(expr)


def test_calculator_divisao_por_zero():
    with pytest.raises(ToolError, match="zero"):
        calculator("1/0")


def test_get_current_time():
    assert get_current_time("UTC").endswith("UTC")
    with pytest.raises(ToolError):
        get_current_time("Marte/Olympus")


def test_lookup_ticket():
    assert "Salesforce" in lookup_ticket("inc0001")
    with pytest.raises(ToolError):
        lookup_ticket("INC9999")


def test_execute_tool_nunca_levanta_excecao():
    assert execute_tool("calculator", {"expression": "1+1"}) == ("2", False)
    assert execute_tool("calculator", {"expression": "1/0"})[1] is True
    assert execute_tool("nao_existe", {})[1] is True
    assert execute_tool("calculator", {"errado": "1"})[1] is True


def test_definicoes_para_api_e_sdk():
    defs = anthropic_tool_definitions()
    assert {d["name"] for d in defs} == set(TOOLS)
    assert all(d["input_schema"]["type"] == "object" for d in defs)
    assert "mcp__lab__calculator" in sdk_tool_names()
