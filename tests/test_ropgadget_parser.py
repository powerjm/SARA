"""Tests for the ROPgadget output parser.

The parser is the most likely place for ROPgadget version drift to break us.
These tests pin its behaviour against captured fixtures so a future
ROPgadget release that changes output format triggers a CI failure rather
than silent miscounts.
"""

from __future__ import annotations

from mcp_servers.ropgadget.parser import Gadget, parse_gadgets

SAMPLE_OUTPUT = """\
Gadgets information
============================================================
0x00000000004011a0 : pop rdi ; ret
0x00000000004011a2 : pop rsi ; pop r15 ; ret
0x00000000004011b0 : mov rax, qword ptr [rdi] ; ret
0x00000000004011c0 : xor eax, eax ; ret

Unique gadgets found: 4
"""


def test_parse_gadgets_basic() -> None:
    gadgets = parse_gadgets(SAMPLE_OUTPUT)
    assert len(gadgets) == 4
    assert gadgets[0] == Gadget(
        address="0x00000000004011a0",
        instructions="pop rdi ; ret",
        length=2,
    )


def test_parse_gadgets_counts_instructions_by_semicolon() -> None:
    gadgets = parse_gadgets(SAMPLE_OUTPUT)
    assert gadgets[1].length == 3  # pop rsi ; pop r15 ; ret
    assert gadgets[2].length == 2  # mov rax,... ; ret


def test_parse_gadgets_canonicalises_addresses_to_lowercase() -> None:
    output = (
        "Gadgets information\n================\n0x00000000004011A0 : RET\nUnique gadgets found: 1\n"
    )
    gadgets = parse_gadgets(output)
    assert gadgets[0].address == "0x00000000004011a0"


def test_parse_gadgets_stops_at_footer() -> None:
    output = SAMPLE_OUTPUT + "0xdeadbeef : ret\n"  # after the footer; ignore
    gadgets = parse_gadgets(output)
    assert len(gadgets) == 4


def test_parse_gadgets_skips_garbage_lines() -> None:
    output = (
        "Gadgets information\n"
        "================\n"
        "not a gadget line\n"
        "0x00000000004011a0 : ret\n"
        "another junk line\n"
        "Unique gadgets found: 1\n"
    )
    gadgets = parse_gadgets(output)
    assert len(gadgets) == 1
    assert gadgets[0].address == "0x00000000004011a0"


def test_parse_gadgets_empty_input() -> None:
    assert parse_gadgets("") == []


def test_parse_gadgets_without_section_header() -> None:
    # If the section header is missing, the parser conservatively returns nothing.
    output = "0x00000000004011a0 : ret\n"
    assert parse_gadgets(output) == []
