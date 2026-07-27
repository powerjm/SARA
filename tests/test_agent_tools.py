# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the agent tool layer (`agent.tools`), Trial-3 curated surface (ADR 0019)."""

from __future__ import annotations

import pytest

from agent.tools import (
    ADDITIONAL_SERVERS,
    FIND_GADGET,
    RUN_SCRIPT,
    SUBMIT_PAYLOAD,
    ToolCall,
    ToolLayer,
    _inject_binary_path,
    normalize_tool_call,
    parse_chain_addresses,
    parse_text_actions,
)
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import FindResult


def _result(**kwargs: object) -> FindResult:
    base: dict[str, object] = {
        "binary_path": "/bin/target",
        "query": "pop rdi; ret",
        "total_found": 2,
        "returned": 2,
        "truncated": False,
        "gadgets": [Gadget("0x4011ad", "pop rdi ; ret", 2), Gadget("0x4011ae", "ret", 1)],
    }
    base.update(kwargs)
    return FindResult(**base)  # type: ignore[arg-type]


# --- tool-exposure premise (Trial 2 §7 gate; the curated set is the contract) --- #
#
# The advertised set must equal the configured toolset, whatever it is, so the
# seam can never silently drift from the config. Trial 3 curated the default to a
# lean ~8 tools (ADR 0019): find_gadget + submit_payload + run_exploit_script, plus
# radare2 (recon, disassemble_at) and gdb (inspect/breakpoint/disassemble).


def test_curated_default_is_about_eight_tools() -> None:
    names = [spec.name for spec in ToolLayer().specs()]
    # No duplicate names in the flat namespace.
    assert len(names) == len(set(names))
    nameset = set(names)
    # The three always-present tools.
    assert {FIND_GADGET, SUBMIT_PAYLOAD, RUN_SCRIPT} <= nameset
    # The curated additional servers each contribute at least one namespaced tool.
    for server in ADDITIONAL_SERVERS:
        assert any(n.startswith(f"{server}_") for n in nameset), server
    # Concrete load-bearing tools of the curated set are reachable.
    assert "radare2_recon" in nameset
    assert "radare2_disassemble_at" in nameset
    assert "gdb_disassemble" in nameset
    # The lean target: around eight tools, not the old 22.
    assert len(names) <= 9


def test_curated_default_drops_pwntools_and_ropper_and_ghidra() -> None:
    nameset = {spec.name for spec in ToolLayer().specs()}
    # pwntools + ropper agent tools were removed; ghidra is opt-in, not default.
    assert not any(n.startswith("pwntools_") for n in nameset)
    assert not any(n.startswith("ropper_") for n in nameset)
    assert not any(n.startswith("ghidra_") for n in nameset)
    # The three gadget dumps collapsed into one query-only find_gadget.
    assert "ropper_enumerate_gadgets" not in nameset
    assert FIND_GADGET in nameset


def test_ghidra_is_available_opt_in() -> None:
    layer = ToolLayer(servers=("radare2", "gdb", "ghidra"))
    names = {spec.name for spec in layer.specs()}
    assert "ghidra_decompile_function" in names


def test_removed_servers_are_rejected_loudly() -> None:
    # pwntools/ropper are no longer agent tool servers -> requesting them raises.
    for gone in ("pwntools", "ropper"):
        with pytest.raises(ValueError, match="unknown tool server"):
            ToolLayer(servers=(gone,))


def test_specs_match_tool_names_exactly() -> None:
    # The premise the pre-flight gate asserts: advertised specs == enabled toolset.
    layer = ToolLayer()
    assert {spec.name for spec in layer.specs()} == layer.tool_names()


def test_servers_subset_narrows_the_toolset() -> None:
    layer = ToolLayer(servers=("gdb",))
    names = {spec.name for spec in layer.specs()}
    assert {FIND_GADGET, SUBMIT_PAYLOAD} <= names
    assert any(n.startswith("gdb_") for n in names)
    assert not any(n.startswith("radare2_") for n in names)


def test_unknown_server_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown tool server"):
        ToolLayer(servers=("bogus",))


def test_dispatch_namespaced_tool_routes_to_owning_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.tools as tools_mod

    def cap(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"routed": tool_name, "args": arguments}

    monkeypatch.setitem(tools_mod._SERVER_DISPATCH, "radare2", cap)
    obs = ToolLayer().dispatch("radare2_recon", {}, binary_path="/bin/target")
    assert obs.tool_name == "radare2_recon"
    assert not obs.output.startswith("ERROR")
    assert "recon" in obs.output


def test_dispatch_namespaced_tool_captures_error_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.tools as tools_mod

    def boom(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("radare2 not on PATH")

    monkeypatch.setitem(tools_mod._SERVER_DISPATCH, "radare2", boom)
    obs = ToolLayer().dispatch("radare2_recon", {}, binary_path="/bin/target")
    assert obs.output.startswith("ERROR")
    assert not obs.truncated


def test_dispatch_disabled_server_tool_is_unknown() -> None:
    # A tool whose server is not enabled is not dispatchable.
    layer = ToolLayer(servers=("gdb",))
    obs = layer.dispatch("radare2_recon", {}, binary_path="/bin/target")
    assert "unknown tool" in obs.output


def test_tool_names_reflects_enabled_servers() -> None:
    # With no additional servers, only the three always-present tools remain.
    assert ToolLayer(servers=()).tool_names() == {FIND_GADGET, SUBMIT_PAYLOAD, RUN_SCRIPT}
    full = ToolLayer().tool_names()
    assert "radare2_recon" in full
    assert "gdb_inspect_state" in full


def test_submit_spec_requires_payload_hex() -> None:
    layer = ToolLayer()
    submit = next(s for s in layer.specs() if s.name == SUBMIT_PAYLOAD)
    assert submit.input_schema["required"] == ["payload_hex"]
    assert submit.input_schema["additionalProperties"] is False


# --- find_gadget: the query-only gadget finder (ADR 0019) ------------------- #


def test_find_gadget_spec_is_query_only() -> None:
    spec = next(s for s in ToolLayer().specs() if s.name == FIND_GADGET)
    # query is required; binary_path is stripped (harness-injected, ADR 0018).
    assert "query" in spec.input_schema["properties"]
    assert "query" in spec.input_schema["required"]
    assert "binary_path" not in spec.input_schema["properties"]


def test_dispatch_find_gadget_returns_terse_matches() -> None:
    layer = ToolLayer(find_fn=lambda **_: _result())
    obs = layer.dispatch(FIND_GADGET, {"query": "pop rdi; ret"}, binary_path="/bin/target")
    assert obs.tool_name == FIND_GADGET
    assert not obs.truncated
    assert "0x4011ad: pop rdi ; ret" in obs.output
    assert "0x4011ae: ret" in obs.output


def test_dispatch_find_gadget_truncates_to_observation_budget() -> None:
    big = _result(
        gadgets=[Gadget(f"0x{i:06x}", "pop rdi ; ret", 2) for i in range(2000)],
        total_found=2000,
        returned=2000,
    )
    layer = ToolLayer(find_fn=lambda **_: big, max_observation_chars=200)
    obs = layer.dispatch(FIND_GADGET, {"query": "pop rdi"}, binary_path="/bin/target")
    assert obs.truncated
    assert len(obs.output) == 200


def test_dispatch_find_gadget_captures_tool_error_instead_of_raising() -> None:
    def boom(**_: object) -> FindResult:
        raise FileNotFoundError("binary not found: /nope")

    layer = ToolLayer(find_fn=boom)
    obs = layer.dispatch(FIND_GADGET, {"query": "ret"}, binary_path="/nope")
    assert obs.output.startswith("ERROR: FileNotFoundError")
    assert not obs.truncated


# --- ADR 0018: the harness injects the staged binary path ------------------- #


def test_specs_strip_binary_path_from_analysis_tools() -> None:
    specs = {s.name: s for s in ToolLayer(servers=("radare2", "gdb", "ghidra")).specs()}
    for name in (
        FIND_GADGET,
        "radare2_recon",
        "radare2_disassemble_at",
        "ghidra_list_imports",
        "gdb_inspect_state",
    ):
        schema = specs[name].input_schema
        assert "binary_path" not in schema.get("properties", {}), name
        assert "binary_path" not in schema.get("required", []), name


def test_specs_do_not_mutate_server_owned_schemas() -> None:
    # Advertising a stripped copy must not clobber the server-owned schema — the
    # standalone MCP stdio servers still require binary_path from their own clients.
    from mcp_servers.radare2 import server as radare2

    ToolLayer().specs()
    assert "binary_path" in radare2.RECON_SCHEMA["properties"]
    assert "binary_path" in radare2.RECON_SCHEMA["required"]


def test_dispatch_injects_staged_path_over_model_value_on_find_gadget() -> None:
    captured: dict[str, object] = {}

    def cap(**kwargs: object) -> FindResult:
        captured.update(kwargs)
        return _result()

    layer = ToolLayer(find_fn=cap)
    # The model asks for the sandbox-only path; the staged host path must win.
    layer.dispatch(
        FIND_GADGET,
        {"query": "ret", "binary_path": "/work/target"},
        binary_path="/staged/target",
    )
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
        "radare2_recon", {"binary_path": "/work/target"}, binary_path="/staged/target"
    )
    assert captured["binary_path"] == "/staged/target"


def test_inject_binary_path_skips_a_schema_without_it() -> None:
    # A tool schema that declares no binary_path is passed through untouched.
    schema = {"type": "object", "properties": {"address": {"type": "string"}}}
    out = _inject_binary_path({"address": "0x1"}, schema, "/staged/target")
    assert "binary_path" not in out
    assert out == {"address": "0x1"}


def test_dispatch_unknown_tool_returns_error_observation() -> None:
    obs = ToolLayer().dispatch("ghidra_decompile", {}, binary_path="/bin/target")
    assert "unknown tool" in obs.output


def test_dispatch_submit_is_terminal_and_raises() -> None:
    with pytest.raises(ValueError, match="terminal"):
        ToolLayer().dispatch(SUBMIT_PAYLOAD, {"payload_hex": "41"}, binary_path="/bin/target")


def test_run_exploit_script_is_advertised() -> None:
    layer = ToolLayer(servers=())
    names = {s.name for s in layer.specs()}
    assert RUN_SCRIPT in names
    spec = next(s for s in layer.specs() if s.name == RUN_SCRIPT)
    assert spec.input_schema["required"] == ["script"]
    assert spec.input_schema["additionalProperties"] is False


def test_dispatch_run_script_is_terminal_and_raises() -> None:
    with pytest.raises(ValueError, match="terminal"):
        ToolLayer().dispatch(RUN_SCRIPT, {"script": "print(1)"}, binary_path="/bin/target")


def test_parse_text_actions_recovers_run_exploit_script_by_default() -> None:
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
    call = normalize_tool_call({"id": "abc", "name": FIND_GADGET, "input": {"query": "ret"}})
    assert call == ToolCall(id="abc", name=FIND_GADGET, arguments={"query": "ret"})


def test_normalize_tool_call_openai_shape_and_missing_id() -> None:
    call = normalize_tool_call({"name": SUBMIT_PAYLOAD, "arguments": {"payload_hex": "41"}})
    assert call.id == ""
    assert call.name == SUBMIT_PAYLOAD
    assert call.arguments == {"payload_hex": "41"}


# --- parse_text_actions (ADR 0010) ----------------------------------------- #


def test_parse_text_actions_react_find_gadget() -> None:
    text = 'Thought: I need the pop rdi gadget.\nAction: find_gadget({"query": "pop rdi; ret"})'
    calls = parse_text_actions(text)
    assert len(calls) == 1
    assert calls[0]["name"] == FIND_GADGET
    assert calls[0]["arguments"] == {"query": "pop rdi; ret"}
    assert normalize_tool_call(calls[0]).name == FIND_GADGET


def test_parse_text_actions_cot_uppercase_submit() -> None:
    text = 'THOUGHT: chain complete.\nACTION: submit_payload({"payload_hex": "deadbeef"})'
    calls = parse_text_actions(text)
    assert [c["name"] for c in calls] == [SUBMIT_PAYLOAD]
    assert calls[0]["arguments"] == {"payload_hex": "deadbeef"}


def test_parse_text_actions_empty_args() -> None:
    calls = parse_text_actions("Action: find_gadget()")
    assert calls == [{"id": "text-action-0", "name": FIND_GADGET, "arguments": {}}]


def test_parse_text_actions_multiple_in_order() -> None:
    text = 'Action: find_gadget({"query": "ret"})\nAction: submit_payload({"payload_hex": "41"})'
    calls = parse_text_actions(text)
    assert [c["id"] for c in calls] == ["text-action-0", "text-action-1"]
    assert [c["name"] for c in calls] == [FIND_GADGET, SUBMIT_PAYLOAD]


def test_parse_text_actions_quote_aware_paren_inside_string() -> None:
    text = 'Action: submit_payload({"payload_hex": "41", "note": "gate(2) reached"})'
    calls = parse_text_actions(text)
    assert calls[0]["arguments"] == {"payload_hex": "41", "note": "gate(2) reached"}


def test_parse_text_actions_tolerates_trailing_prose_in_parens() -> None:
    text = 'Action: find_gadget({"query": "ret"} to see more)'
    assert parse_text_actions(text)[0]["arguments"] == {"query": "ret"}


def test_parse_text_actions_ignores_prose_and_unknown_tools() -> None:
    assert parse_text_actions("Just analysis, no action lines here.") == []
    assert parse_text_actions('The reaction: find_gadget({"query": "ret"})') == []
    assert parse_text_actions("Action: ghidra_decompile({})") == []


def test_parse_text_actions_skips_unbalanced_parens() -> None:
    assert parse_text_actions('Action: find_gadget({"query": "ret"') == []


def test_parse_text_actions_empty_and_none() -> None:
    assert parse_text_actions("") == []
    assert parse_text_actions(None) == []


# --- parse_text_actions: JSON-object form (ADR 0010, broadened) ------------- #


def test_parse_text_actions_json_block() -> None:
    text = (
        "Here is my call:\n"
        '```json\n{"name": "find_gadget", "arguments": {"query": "syscall; ret"}}\n```\n'
        "Now I continue."
    )
    calls = parse_text_actions(text)
    assert len(calls) == 1
    assert calls[0]["name"] == FIND_GADGET
    assert calls[0]["arguments"] == {"query": "syscall; ret"}


def test_parse_text_actions_json_object_input_and_parameters_keys() -> None:
    a = parse_text_actions('{"name": "submit_payload", "input": {"payload_hex": "41"}}')
    assert a[0]["arguments"] == {"payload_hex": "41"}
    b = parse_text_actions('{"name": "find_gadget", "parameters": {"query": "ret"}}')
    assert b[0]["arguments"] == {"query": "ret"}


def test_parse_text_actions_json_object_missing_args_is_empty() -> None:
    calls = parse_text_actions('{"name": "find_gadget"}')
    assert calls == [{"id": "text-action-0", "name": FIND_GADGET, "arguments": {}}]


def test_parse_text_actions_ignores_non_toolcall_json() -> None:
    assert parse_text_actions('{"type": "object", "properties": {"x": {"type": "string"}}}') == []
    assert parse_text_actions('{"name": "ghidra_decompile", "arguments": {}}') == []


# --- parse_text_actions: namespaced tools honor the enabled `known` set -------- #


def test_parse_text_actions_recovers_namespaced_tool_when_known() -> None:
    text = 'Action: radare2_recon({"max_strings": 20})'
    known = ToolLayer().tool_names()
    calls = parse_text_actions(text, known=known)
    assert len(calls) == 1
    assert calls[0]["name"] == "radare2_recon"
    assert calls[0]["arguments"] == {"max_strings": 20}


def test_parse_text_actions_ignores_namespaced_tool_by_default() -> None:
    # Without the enabled set, only the three core tools are recognized (back-compat).
    text = 'Action: radare2_recon({"max_strings": 20})'
    assert parse_text_actions(text) == []
    # And a tool whose server is disabled is not recovered even with a `known` set.
    known = ToolLayer(servers=("gdb",)).tool_names()
    assert parse_text_actions(text, known=known) == []
