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
    ADDITIONAL_SERVERS,
    ENUMERATE_GADGETS,
    RUN_SCRIPT,
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


# --- tool-exposure premise (Trial 2 §7 gate; replaces the stale two-tool lock) --- #
#
# Trial 1 shipped with `specs()` hardcoded to exactly {enumerate_gadgets,
# submit_payload}, and a test asserting that exact equality — so wiring the other
# five servers would have *broken a green test*. These tests instead assert that
# the advertised set equals the configured toolset, whatever it is, so the seam
# can never silently drift from the config again.


def test_specs_advertise_core_plus_all_servers_by_default() -> None:
    layer = ToolLayer()
    names = [spec.name for spec in layer.specs()]
    # No duplicate names in the flat tool namespace (the ropgadget/ropper
    # `enumerate_gadgets` collision is resolved by namespacing).
    assert len(names) == len(set(names))
    nameset = set(names)
    # The two always-present tools keep their bare, graph-special names.
    assert {ENUMERATE_GADGETS, SUBMIT_PAYLOAD} <= nameset
    # Every additional server contributes at least one namespaced tool.
    for server in ADDITIONAL_SERVERS:
        assert any(n.startswith(f"{server}_") for n in nameset), server
    # A couple of concrete, load-bearing tools are reachable by name.
    assert "pwntools_build_payload" in nameset
    assert "ghidra_decompile_function" in nameset
    # ropper's enumerate_gadgets is namespaced; ropgadget's is not.
    assert "ropper_enumerate_gadgets" in nameset


def test_specs_match_tool_names_exactly() -> None:
    # The premise the pre-flight gate asserts: advertised specs == enabled toolset.
    layer = ToolLayer()
    assert {spec.name for spec in layer.specs()} == layer.tool_names()


def test_servers_subset_narrows_the_toolset() -> None:
    layer = ToolLayer(servers=("pwntools",))
    names = {spec.name for spec in layer.specs()}
    assert {ENUMERATE_GADGETS, SUBMIT_PAYLOAD} <= names
    assert any(n.startswith("pwntools_") for n in names)
    assert not any(n.startswith("radare2_") for n in names)
    assert not any(n.startswith("ghidra_") for n in names)


def test_unknown_server_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown tool server"):
        ToolLayer(servers=("bogus",))


def test_dispatch_namespaced_tool_routes_to_owning_server() -> None:
    # pwntools tools are pure (no native dep / subprocess), so this exercises the
    # real server dispatch end-to-end in CI.
    layer = ToolLayer()
    obs = layer.dispatch(
        "pwntools_pack_address", {"address": "0x4011ad", "arch": "amd64"}, binary_path="/bin/target"
    )
    assert obs.tool_name == "pwntools_pack_address"
    assert not obs.output.startswith("ERROR")
    assert "ad11400000000000" in obs.output  # 0x4011ad packed little-endian, 8 bytes


def test_dispatch_namespaced_tool_captures_error_instead_of_raising() -> None:
    layer = ToolLayer()
    obs = layer.dispatch(
        "pwntools_pack_address", {"address": "not-a-number"}, binary_path="/bin/target"
    )
    assert obs.output.startswith("ERROR")
    assert not obs.truncated


def test_dispatch_disabled_server_tool_is_unknown() -> None:
    # A tool whose server is not enabled is not dispatchable.
    layer = ToolLayer(servers=("pwntools",))
    obs = layer.dispatch("radare2_analyze_binary", {}, binary_path="/bin/target")
    assert "unknown tool" in obs.output


def test_tool_names_reflects_enabled_servers() -> None:
    # With no additional servers, only the three always-present tools remain.
    assert ToolLayer(servers=()).tool_names() == {ENUMERATE_GADGETS, SUBMIT_PAYLOAD, RUN_SCRIPT}
    full = ToolLayer().tool_names()
    assert "radare2_search_pattern" in full
    assert "gdb_inspect_state" in full


def test_submit_spec_requires_payload_hex() -> None:
    layer = ToolLayer()
    submit = next(s for s in layer.specs() if s.name == SUBMIT_PAYLOAD)
    assert submit.input_schema["required"] == ["payload_hex"]
    assert submit.input_schema["additionalProperties"] is False


def test_dispatch_enumerate_returns_observation_with_addresses() -> None:
    layer = ToolLayer(enumerate_fn=lambda **_: _result())
    obs = layer.dispatch(ENUMERATE_GADGETS, {}, binary_path="/bin/target")
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
    obs = layer.dispatch(ENUMERATE_GADGETS, {}, binary_path="/bin/target")
    assert obs.truncated
    assert len(obs.output) == 200


def test_dispatch_captures_tool_error_instead_of_raising() -> None:
    def boom(**_: object) -> EnumerateResult:
        raise FileNotFoundError("binary not found: /nope")

    layer = ToolLayer(enumerate_fn=boom)
    obs = layer.dispatch(ENUMERATE_GADGETS, {}, binary_path="/nope")
    assert obs.output.startswith("ERROR: FileNotFoundError")
    assert not obs.truncated


# --- ADR 0018: the harness injects the staged binary path; the model neither ---- #
# --- supplies nor sees it. The analysis tools run on the host, where the model's -- #
# --- sandbox-only /work/target does not exist, and confining them to the staged --- #
# --- target keeps a host-side tool from being pointed at an arbitrary file. ------- #


def test_specs_strip_binary_path_from_analysis_tools() -> None:
    specs = {s.name: s for s in ToolLayer().specs()}
    for name in (
        ENUMERATE_GADGETS,
        "radare2_analyze_binary",
        "ghidra_list_imports",
        "ropper_get_strings",
        "gdb_inspect_state",
    ):
        schema = specs[name].input_schema
        assert "binary_path" not in schema.get("properties", {}), name
        assert "binary_path" not in schema.get("required", []), name
    # A pure pwntools helper never took binary_path and is left alone.
    assert "binary_path" not in specs["pwntools_pack_address"].input_schema.get("properties", {})


def test_specs_do_not_mutate_server_owned_schemas() -> None:
    # Advertising a stripped copy must not clobber the server-owned schema — the
    # standalone MCP stdio servers still require binary_path from their own clients.
    from mcp_servers.radare2 import server as radare2

    ToolLayer().specs()
    assert "binary_path" in radare2.ANALYZE_BINARY_SCHEMA["properties"]
    assert "binary_path" in radare2.ANALYZE_BINARY_SCHEMA["required"]


def test_dispatch_injects_staged_path_over_model_value_on_enumerate() -> None:
    captured: dict[str, object] = {}

    def cap(**kwargs: object) -> EnumerateResult:
        captured.update(kwargs)
        return _result()

    layer = ToolLayer(enumerate_fn=cap)
    # The model asks for the sandbox-only path; the staged host path must win.
    layer.dispatch(ENUMERATE_GADGETS, {"binary_path": "/work/target"}, binary_path="/staged/target")
    assert captured["binary_path"] == "/staged/target"


def test_dispatch_injects_staged_path_for_namespaced_analysis_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.tools as tools_mod

    captured: dict[str, object] = {}

    def cap(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured.update(arguments)
        return {"ok": True}

    monkeypatch.setitem(tools_mod._SERVER_DISPATCH, "radare2", cap)
    ToolLayer().dispatch(
        "radare2_analyze_binary", {"binary_path": "/work/target"}, binary_path="/staged/target"
    )
    assert captured["binary_path"] == "/staged/target"


def test_dispatch_does_not_inject_binary_path_into_pure_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.tools as tools_mod

    captured: dict[str, object] = {}

    def cap(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        captured.update(arguments)
        return {"ok": True}

    monkeypatch.setitem(tools_mod._SERVER_DISPATCH, "pwntools", cap)
    ToolLayer().dispatch("pwntools_pack_address", {"address": "0x1"}, binary_path="/staged/target")
    assert "binary_path" not in captured


def test_dispatch_unknown_tool_returns_error_observation() -> None:
    obs = ToolLayer().dispatch("ghidra_decompile", {}, binary_path="/bin/target")
    assert "unknown tool" in obs.output


def test_dispatch_submit_is_terminal_and_raises() -> None:
    with pytest.raises(ValueError, match="terminal"):
        ToolLayer().dispatch(SUBMIT_PAYLOAD, {"payload_hex": "41"}, binary_path="/bin/target")


def test_run_exploit_script_is_advertised() -> None:
    # run_exploit_script (ADR 0016) is a third always-present tool, requiring a
    # 'script' string, present even with no additional servers.
    layer = ToolLayer(servers=())
    names = {s.name for s in layer.specs()}
    assert RUN_SCRIPT in names
    spec = next(s for s in layer.specs() if s.name == RUN_SCRIPT)
    assert spec.input_schema["required"] == ["script"]
    assert spec.input_schema["additionalProperties"] is False


def test_dispatch_run_script_is_terminal_and_raises() -> None:
    # Like submit_payload, it is committed via the propose node, never dispatched.
    with pytest.raises(ValueError, match="terminal"):
        ToolLayer().dispatch(RUN_SCRIPT, {"script": "print(1)"}, binary_path="/bin/target")


def test_parse_text_actions_recovers_run_exploit_script_by_default() -> None:
    # run_exploit_script is in the default known set, so a prose call is recovered.
    text = 'Action: run_exploit_script({"script": "from pwn import *"})'
    calls = parse_text_actions(text)
    assert [c["name"] for c in calls] == [RUN_SCRIPT]
    assert calls[0]["arguments"] == {"script": "from pwn import *"}


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


# --- parse_text_actions: namespaced tools honor the enabled `known` set -------- #


def test_parse_text_actions_recovers_namespaced_tool_when_known() -> None:
    text = 'Action: radare2_analyze_binary({"binary_path": "/work/bin"})'
    known = ToolLayer().tool_names()
    calls = parse_text_actions(text, known=known)
    assert len(calls) == 1
    assert calls[0]["name"] == "radare2_analyze_binary"
    assert calls[0]["arguments"] == {"binary_path": "/work/bin"}


def test_parse_text_actions_ignores_namespaced_tool_by_default() -> None:
    # Without the enabled set, only the two core tools are recognized (back-compat).
    text = 'Action: radare2_analyze_binary({"binary_path": "/work/bin"})'
    assert parse_text_actions(text) == []
    # And a tool whose server is disabled is not recovered even with a `known` set.
    known = ToolLayer(servers=("pwntools",)).tool_names()
    assert parse_text_actions(text, known=known) == []
