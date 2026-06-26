"""Tests for the radare2 MCP server (pure parsers + skipped integration)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_servers.radare2 import server as r2

_FIXTURE_BINARY = Path(__file__).resolve().parent / "fixtures" / "binaries" / "sample_overflow"

_AFLJ = json.dumps(
    [
        {"name": "sym.win", "offset": 0x401166, "size": 71},
        {"name": "main", "offset": 0x4011D0, "size": 42},
        {"bogus": "no offset"},  # skipped permissively
    ]
)

_PDJ = json.dumps(
    [
        {"offset": 0x401166, "disasm": "push rbp", "bytes": "55"},
        {"offset": 0x401167, "opcode": "mov rbp, rsp", "bytes": "4889e5"},
    ]
)

# radare2 6.0 (shipped on Ubuntu 26.04) renamed the address field `offset` ->
# `addr` in aflj/pdj/search. These canned outputs pin the 6.x schema so the
# parsers stay compatible with both lines (regression for the silent
# zero-results bug against a 6.x radare2).
_AFLJ_V6 = json.dumps(
    [
        {"name": "sym.win", "addr": 0x401166, "size": 71},
        {"name": "main", "addr": 0x4011D0, "size": 42},
    ]
)

_PDJ_V6 = json.dumps(
    [
        {"addr": 0x401166, "disasm": "push rbp", "bytes": "55"},
        {"addr": 0x401167, "opcode": "mov rbp, rsp", "bytes": "4889e5"},
    ]
)

_IJ = json.dumps(
    {
        "bin": {
            "arch": "x86",
            "bits": 64,
            "os": "linux",
            "bintype": "elf",
            "canary": False,
            "nx": True,
            "pic": False,
        }
    }
)


def test_parse_functions() -> None:
    functions = r2.parse_functions(_AFLJ)
    assert len(functions) == 2
    assert functions[0] == r2.Function(name="sym.win", offset=0x401166, size=71)
    assert functions[1].name == "main"


def test_parse_functions_empty() -> None:
    assert r2.parse_functions("") == []
    assert r2.parse_functions("[]") == []


def test_parse_functions_radare2_6_addr_field() -> None:
    """radare2 6.x emits `addr` instead of `offset`; both must parse."""
    functions = r2.parse_functions(_AFLJ_V6)
    assert len(functions) == 2
    assert functions[0] == r2.Function(name="sym.win", offset=0x401166, size=71)
    assert {f.name for f in functions} == {"sym.win", "main"}


def test_parse_disasm_radare2_6_addr_field() -> None:
    instructions = r2.parse_disasm(_PDJ_V6)
    assert [i.offset for i in instructions] == [0x401166, 0x401167]
    assert instructions[0].opcode == "push rbp"


def test_parse_disasm_prefers_disasm_then_opcode() -> None:
    instructions = r2.parse_disasm(_PDJ)
    assert instructions[0].opcode == "push rbp"
    assert instructions[1].opcode == "mov rbp, rsp"
    assert instructions[1].bytes == "4889e5"


def test_parse_analysis_bin_nesting() -> None:
    info = r2.parse_analysis(_IJ)
    assert info.arch == "x86"
    assert info.bits == 64
    assert info.nx is True
    assert info.canary is False


def test_parse_analysis_flat_shape() -> None:
    flat = json.dumps({"arch": "x86", "bits": 32, "os": "linux"})
    info = r2.parse_analysis(flat)
    assert info.bits == 32


def test_result_to_dict_helpers() -> None:
    functions = r2.parse_functions(_AFLJ)
    result = r2.FunctionsResult(
        binary_path="/b", total_found=2, returned=2, truncated=False, functions=functions
    )
    payload = r2.functions_result_to_dict(result)
    assert payload["total_found"] == 2
    assert payload["functions"][0]["name"] == "sym.win"


@pytest.mark.requires_radare2
def test_list_functions_integration() -> None:
    result = r2.list_functions(str(_FIXTURE_BINARY))
    names = {f.name for f in result.functions}
    assert any("main" in name for name in names)


@pytest.mark.requires_radare2
def test_analyze_binary_integration() -> None:
    result = r2.analyze_binary(str(_FIXTURE_BINARY))
    assert result.info.bits == 64
    assert result.function_count > 0
