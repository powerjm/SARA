# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the Trial-3 query-only ``find_gadget`` finder (ADR 0019).

``find_gadget`` compiles a named gadget query to an instruction-text regex and
runs it through the ROPgadget engine. The compilation (``_query_to_regex``) is the
testable core — the CLI shell-out is covered by the ropgadget integration test —
so these pin the query semantics and the terse result mapping without ROPgadget.
"""

from __future__ import annotations

import re

import pytest

from mcp_servers.ropgadget import server as ropgadget
from mcp_servers.ropgadget.parser import Gadget


def _match(query: str, instructions: str) -> bool:
    return re.search(ropgadget._query_to_regex(query), instructions, re.IGNORECASE) is not None


def test_query_ordered_steps_allow_intervening_instructions() -> None:
    # "pop rdi; ret" matches an exact gadget and one with an intervening insn.
    assert _match("pop rdi; ret", "pop rdi ; ret")
    assert _match("pop rdi; ret", "pop rdi ; nop ; ret")
    # But order matters: ret-before-pop does not match.
    assert not _match("pop rdi; ret", "ret ; pop rdi")


def test_query_is_case_insensitive_and_whitespace_flexible() -> None:
    assert _match("POP RDI ; RET", "pop  rdi ;  ret")


def test_query_reg_is_a_register_wildcard() -> None:
    assert _match("pop reg; ret", "pop rsi ; ret")
    assert _match("pop reg; ret", "pop r15 ; ret")
    assert _match("mov [reg], reg; ret", "mov [rdi], rsi ; ret")
    # A concrete register in the query does NOT act as a wildcard.
    assert not _match("pop rdi; ret", "pop rsi ; ret")


def test_query_special_chars_are_matched_literally() -> None:
    assert _match("mov qword ptr [rdi], rax", "mov qword ptr [rdi], rax ; ret")


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty gadget query"):
        ropgadget._query_to_regex("   ;  ")


def test_find_gadget_passes_compiled_query_and_maps_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_enumerate(binary_path: str, **kwargs: object) -> ropgadget.EnumerateResult:
        captured.update(kwargs)
        captured["binary_path"] = binary_path
        return ropgadget.EnumerateResult(
            binary_path=binary_path,
            total_found=1,
            returned=1,
            truncated=False,
            gadgets=[Gadget("0x4011a0", "pop rdi ; ret", 2)],
        )

    monkeypatch.setattr(ropgadget, "enumerate_gadgets", fake_enumerate)
    result = ropgadget.find_gadget("/bin/target", "pop rdi; ret", max_results=32)
    # The query was compiled to a regex and handed to the engine as filter_regex.
    assert captured["filter_regex"] == ropgadget._query_to_regex("pop rdi; ret")
    assert captured["max_results"] == 32
    assert result.query == "pop rdi; ret"
    assert result.returned == 1
    assert result.gadgets[0].address == "0x4011a0"


def test_find_result_to_dict_is_terse() -> None:
    result = ropgadget.FindResult(
        binary_path="/bin/target",
        query="ret",
        total_found=1,
        returned=1,
        truncated=False,
        gadgets=[Gadget("0x401166", "ret", 1)],
    )
    d = ropgadget.find_result_to_dict(result)
    # Terse rows: address + instructions only (no length field re-billed).
    assert d["gadgets"] == [{"address": "0x401166", "instructions": "ret"}]
    assert d["query"] == "ret"
