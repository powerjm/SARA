# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

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
    parse_text_actions,
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


# --- parse_text_actions (ADR 0010) ----------------------------------------- #


def test_parse_text_actions_react_enumerate() -> None:
    text = (
        "Thought: I should look at the pop gadgets first.\n"
        'Action: enumerate_gadgets({"binary_path": "/work/bin", "filter_regex": "pop"})'
    )
    calls = parse_text_actions(text)
    assert len(calls) == 1
    assert calls[0]["name"] == ENUMERATE_GADGETS
    assert calls[0]["arguments"] == {"binary_path": "/work/bin", "filter_regex": "pop"}
    # Native-shaped: an id is present and the dict normalizes like a real call.
    assert normalize_tool_call(calls[0]).name == ENUMERATE_GADGETS


def test_parse_text_actions_cot_uppercase_submit() -> None:
    text = 'THOUGHT: chain complete.\nACTION: submit_payload({"payload_hex": "deadbeef"})'
    calls = parse_text_actions(text)
    assert [c["name"] for c in calls] == [SUBMIT_PAYLOAD]
    assert calls[0]["arguments"] == {"payload_hex": "deadbeef"}


def test_parse_text_actions_empty_args() -> None:
    calls = parse_text_actions("Action: enumerate_gadgets()")
    assert calls == [{"id": "text-action-0", "name": ENUMERATE_GADGETS, "arguments": {}}]


def test_parse_text_actions_multiple_in_order() -> None:
    text = (
        'Action: enumerate_gadgets({"binary_path": "/a"})\n'
        'Action: submit_payload({"payload_hex": "41"})'
    )
    calls = parse_text_actions(text)
    assert [c["id"] for c in calls] == ["text-action-0", "text-action-1"]
    assert [c["name"] for c in calls] == [ENUMERATE_GADGETS, SUBMIT_PAYLOAD]


def test_parse_text_actions_quote_aware_paren_inside_string() -> None:
    # A ")" inside a JSON string must not close the argument group early.
    text = 'Action: submit_payload({"payload_hex": "41", "note": "gate(2) reached"})'
    calls = parse_text_actions(text)
    assert calls[0]["arguments"] == {"payload_hex": "41", "note": "gate(2) reached"}


def test_parse_text_actions_tolerates_trailing_prose_in_parens() -> None:
    text = 'Action: enumerate_gadgets({"binary_path": "/a"} to see more)'
    assert parse_text_actions(text)[0]["arguments"] == {"binary_path": "/a"}


def test_parse_text_actions_ignores_prose_and_unknown_tools() -> None:
    assert parse_text_actions("Just analysis, no action lines here.") == []
    # A word ending in "action:" (e.g. "reaction:") must not trigger a match.
    assert parse_text_actions('The reaction: enumerate_gadgets({"binary_path": "/a"})') == []
    # An unknown tool name is not dispatched.
    assert parse_text_actions("Action: ghidra_decompile({})") == []


def test_parse_text_actions_skips_unbalanced_parens() -> None:
    assert parse_text_actions('Action: enumerate_gadgets({"binary_path": "/a"') == []


def test_parse_text_actions_empty_and_none() -> None:
    assert parse_text_actions("") == []
    assert parse_text_actions(None) == []


# --- parse_text_actions: JSON-object form (ADR 0010, broadened) ------------- #


def test_parse_text_actions_json_block() -> None:
    text = (
        "Here is my call:\n"
        '```json\n{"name": "enumerate_gadgets", "arguments": {"binary_path": "/work/bin"}}\n```\n'
        "Now I continue."
    )
    calls = parse_text_actions(text)
    assert len(calls) == 1
    assert calls[0]["name"] == ENUMERATE_GADGETS
    assert calls[0]["arguments"] == {"binary_path": "/work/bin"}


def test_parse_text_actions_json_object_input_and_parameters_keys() -> None:
    # Accept "input" (Anthropic-ish) and "parameters" as arg-bag aliases.
    a = parse_text_actions('{"name": "submit_payload", "input": {"payload_hex": "41"}}')
    assert a[0]["arguments"] == {"payload_hex": "41"}
    b = parse_text_actions('{"name": "enumerate_gadgets", "parameters": {"binary_path": "/a"}}')
    assert b[0]["arguments"] == {"binary_path": "/a"}


def test_parse_text_actions_json_object_missing_args_is_empty() -> None:
    calls = parse_text_actions('{"name": "enumerate_gadgets"}')
    assert calls == [{"id": "text-action-0", "name": ENUMERATE_GADGETS, "arguments": {}}]


def test_parse_text_actions_ignores_non_toolcall_json() -> None:
    # A schema echo or unrelated object (no known tool name) is not a call.
    assert parse_text_actions('{"type": "object", "properties": {"x": {"type": "string"}}}') == []
    assert parse_text_actions('{"name": "ghidra_decompile", "arguments": {}}') == []
