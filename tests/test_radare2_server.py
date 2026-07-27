# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the radare2 MCP server (pure parsers + skipped integration)."""

from __future__ import annotations

import json
from collections.abc import Iterator
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


# --------------------------------------------------------------------------- #
# recon parsers (ADR 0019) — pure, canned-JSON tested                          #
# --------------------------------------------------------------------------- #

_IIJ = json.dumps(
    {
        "arch": "x86",
        "bits": 64,
        "endian": "little",
        "os": "linux",
        "relro": "partial",
        "nx": True,
        "pic": False,
        "canary": False,
    }
)
_IEJ = json.dumps([{"vaddr": 0x401050, "paddr": 0x1050}])
_IIJ_IMPORTS = json.dumps([{"name": "gets"}, {"name": "puts"}, {"name": "gets"}, {"bogus": "x"}])
_IZJ = json.dumps(
    {"strings": [{"vaddr": 0x402004, "string": "hello"}, {"vaddr": 0x402010, "string": "/bin/sh"}]}
)
_ISJ = json.dumps(
    [
        {"name": ".text", "vaddr": 0x401000, "size": 0x400, "perm": "-r-x"},
        {"name": ".data", "vaddr": 0x404000, "size": 0x40, "perm": "-rw-"},
        {"name": ".bss", "vaddr": 0x404040, "size": 0x20, "perm": "-rw-"},
    ]
)


def test_parse_recon_info_extracts_protections() -> None:
    info = r2.parse_recon_info(_IIJ)
    assert info.arch == "x86"
    assert info.bits == 64
    assert info.endian == "little"
    assert info.relro == "partial"
    assert info.nx is True
    assert info.pie is False


def test_parse_recon_info_handles_bin_nesting() -> None:
    nested = json.dumps({"bin": {"arch": "x86", "bits": 32, "nx": False}})
    info = r2.parse_recon_info(nested)
    assert info.bits == 32
    assert info.nx is False


def test_parse_entrypoint() -> None:
    assert r2.parse_entrypoint(_IEJ) == 0x401050
    assert r2.parse_entrypoint("[]") is None


def test_parse_imports_dedups_in_order() -> None:
    assert r2.parse_imports(_IIJ_IMPORTS) == ["gets", "puts"]


def test_parse_strings_both_shapes() -> None:
    rows = r2.parse_strings(_IZJ)
    assert {r["string"] for r in rows} == {"hello", "/bin/sh"}
    assert rows[1]["address"] == 0x402010
    # Bare-list shape is accepted too.
    bare = json.dumps([{"vaddr": 1, "string": "x"}])
    assert r2.parse_strings(bare)[0]["string"] == "x"


def test_parse_writable_sections_keeps_only_writable() -> None:
    rows = r2.parse_writable_sections(_ISJ)
    names = {r["name"] for r in rows}
    assert names == {".data", ".bss"}  # .text (r-x) excluded
    assert all(r["address"] is not None for r in rows)


# --------------------------------------------------------------------------- #
# Per-run session cache (ADR 0019) — memoization via the injectable opener      #
# --------------------------------------------------------------------------- #


class _FakeSession:
    """Records commands and returns canned JSON keyed by the command prefix."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.cmds: list[str] = []
        self.quit_called = False

    def cmd(self, command: str) -> str:
        self.cmds.append(command)
        for prefix, value in self.responses.items():
            if command.startswith(prefix):
                return value
        return ""

    def quit(self) -> None:
        self.quit_called = True


_RECON_RESPONSES = {
    "iIj": _IIJ,
    "iej": _IEJ,
    "aflj": _AFLJ,
    "iij": _IIJ_IMPORTS,
    "izj": _IZJ,
    "iSj": _ISJ,
}


@pytest.fixture
def _clean_cache() -> Iterator[None]:
    r2.reset_session_cache()
    yield
    r2.reset_session_cache()
    r2._OPENER = None


def test_session_is_memoized_and_analyzed_once(
    tmp_path: Path, _clean_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "target"
    binary.write_bytes(b"\x7fELF fake")
    opens: list[str] = []

    def fake_opener(path: str) -> _FakeSession:
        opens.append(path)
        return _FakeSession(_RECON_RESPONSES)

    monkeypatch.setattr(r2, "_OPENER", fake_opener)

    r1 = r2.recon(str(binary))
    r2_again = r2.recon(str(binary))

    # Opened once (memoized by path+mtime), and `aaa` ran exactly once total.
    assert len(opens) == 1
    session = r2._SESSION_CACHE[str(binary)].session
    assert session.cmds.count("aaa") == 1
    # recon returns the parsed snapshot both times.
    assert r1.info.bits == 64
    assert r2_again.imports == ["gets", "puts"]
    assert any(s["string"] == "/bin/sh" for s in r1.interesting_strings)
    assert {s["name"] for s in r1.writable_sections} == {".data", ".bss"}


def test_session_reopens_when_binary_mtime_changes(
    tmp_path: Path, _clean_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "target"
    binary.write_bytes(b"\x7fELF a")
    opens: list[str] = []

    def fake_opener(path: str) -> _FakeSession:
        opens.append(path)
        return _FakeSession(_RECON_RESPONSES)

    monkeypatch.setattr(r2, "_OPENER", fake_opener)

    r2.recon(str(binary))
    # A rebuilt binary (new mtime) must not reuse the stale analyzed session.
    import os

    st = binary.stat()
    os.utime(binary, (st.st_atime + 5, st.st_mtime + 5))
    r2.recon(str(binary))
    assert len(opens) == 2


def test_recon_interesting_string_kept_beyond_the_cap() -> None:
    strings = [{"address": i, "string": f"pad{i}"} for i in range(5)]
    strings.append({"address": 999, "string": "/bin/sh"})
    kept = r2._select_interesting(strings, limit=3)
    assert any(s["string"] == "/bin/sh" for s in kept)
    assert len(kept) == 4  # first 3 + the relevant one past the cap
