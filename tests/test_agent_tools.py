"""Tests for the agent tool layer (`agent.tools`)."""

from __future__ import annotations

import pytest

from agent.tools import (
    ENUMERATE_GADGETS,
    SUBMIT_PAYLOAD,
    ToolCall,
    ToolLayer,
    normalize_tool_call,
    parse_chain_addresses,
)
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import EnumerateResult


def _result(**kwargs: object) -> EnumerateResult:
    base: dict[str, object] = {
        "binary_path": "/bin/target",
        "total_found": 2,
        "returned": 2,
        "truncated": False,
        "gadgets": [Gadget("0x4011ad", "pop rdi ; ret", 2), Gadget("0x4011ae", "ret", 1)],
    }
    base.update(kwargs)
    return EnumerateResult(**base)  # type: ignore[arg-type]


def test_specs_advertise_enumerate_and_submit() -> None:
    layer = ToolLayer()
    names = {spec.name for spec in layer.specs()}
    assert names == {ENUMERATE_GADGETS, SUBMIT_PAYLOAD}


def test_submit_spec_requires_payload_hex() -> None:
    layer = ToolLayer()
    submit = next(s for s in layer.specs() if s.name == SUBMIT_PAYLOAD)
    assert submit.input_schema["required"] == ["payload_hex"]
    assert submit.input_schema["additionalProperties"] is False


def test_dispatch_enumerate_returns_observation_with_addresses() -> None:
    layer = ToolLayer(enumerate_fn=lambda **_: _result())
    obs = layer.dispatch(ENUMERATE_GADGETS, {"binary_path": "/bin/target"})
    assert obs.tool_name == ENUMERATE_GADGETS
    assert not obs.truncated
    assert "0x4011ad: pop rdi ; ret" in obs.output
    assert "0x4011ae: ret" in obs.output


def test_dispatch_truncates_to_observation_budget() -> None:
    big = _result(
        gadgets=[Gadget(f"0x{i:06x}", "pop rdi ; ret", 2) for i in range(2000)],
        total_found=2000,
        returned=2000,
    )
    layer = ToolLayer(enumerate_fn=lambda **_: big, max_observation_chars=200)
    obs = layer.dispatch(ENUMERATE_GADGETS, {"binary_path": "/bin/target"})
    assert obs.truncated
    assert len(obs.output) == 200


def test_dispatch_captures_tool_error_instead_of_raising() -> None:
    def boom(**_: object) -> EnumerateResult:
        raise FileNotFoundError("binary not found: /nope")

    layer = ToolLayer(enumerate_fn=boom)
    obs = layer.dispatch(ENUMERATE_GADGETS, {"binary_path": "/nope"})
    assert obs.output.startswith("ERROR: FileNotFoundError")
    assert not obs.truncated


def test_dispatch_unknown_tool_returns_error_observation() -> None:
    obs = ToolLayer().dispatch("ghidra_decompile", {})
    assert "unknown tool" in obs.output


def test_dispatch_submit_is_terminal_and_raises() -> None:
    with pytest.raises(ValueError, match="terminal"):
        ToolLayer().dispatch(SUBMIT_PAYLOAD, {"payload_hex": "41"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ([], None),
        (["0x4011ad", "0x401166"], [0x4011AD, 0x401166]),
        (["4011ad"], [0x4011AD]),
        ([0x4011AD, 4198758], [0x4011AD, 4198758]),
        (["0x10", "32"], [0x10, 32]),
    ],
)
def test_parse_chain_addresses(raw: object, expected: list[int] | None) -> None:
    assert parse_chain_addresses(raw) == expected


def test_parse_chain_addresses_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid chain address"):
        parse_chain_addresses(["not-an-address"])


def test_parse_chain_addresses_rejects_bool() -> None:
    with pytest.raises(ValueError, match="invalid chain address"):
        parse_chain_addresses([True])


def test_normalize_tool_call_anthropic_shape() -> None:
    call = normalize_tool_call(
        {"id": "abc", "name": ENUMERATE_GADGETS, "input": {"binary_path": "x"}}
    )
    assert call == ToolCall(id="abc", name=ENUMERATE_GADGETS, arguments={"binary_path": "x"})


def test_normalize_tool_call_openai_shape_and_missing_id() -> None:
    call = normalize_tool_call({"name": SUBMIT_PAYLOAD, "arguments": {"payload_hex": "41"}})
    assert call.id == ""
    assert call.name == SUBMIT_PAYLOAD
    assert call.arguments == {"payload_hex": "41"}
