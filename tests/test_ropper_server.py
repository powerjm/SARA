"""Tests for the ropper MCP server (pure parser/extractor + skipped integration)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.ropper import server as ropper

_FIXTURE_BINARY = Path(__file__).resolve().parent / "fixtures" / "binaries" / "sample_overflow"

_ROPPER_OUTPUT = """\

Gadgets
=======

0x004005a0: pop rdi; ret;
0x004005a2: pop rsi; pop r15; ret;
0x00400520: ret;
this line is not a gadget
0x00400526: leave; ret;

3 gadgets found
"""


def test_parse_gadgets() -> None:
    gadgets = ropper.parse_gadgets(_ROPPER_OUTPUT)
    assert len(gadgets) == 4
    assert gadgets[0] == ropper.Gadget(address="0x004005a0", instructions="pop rdi; ret;", length=2)
    assert gadgets[1].length == 3
    assert gadgets[2].instructions == "ret;"
    assert gadgets[2].length == 1


def test_parse_gadgets_skips_noise() -> None:
    gadgets = ropper.parse_gadgets("no gadgets here\nbanner only\n")
    assert gadgets == []


def test_parse_gadgets_lowercases_address() -> None:
    gadgets = ropper.parse_gadgets("0x00ABCDEF: ret;\n")
    assert gadgets[0].address == "0x00abcdef"


def test_extract_ascii_strings() -> None:
    data = b"\x00\x01Hello\x00World!!\x02ab"  # "ab" too short for min_len=4
    strings = ropper.extract_ascii_strings(data, min_len=4)
    assert strings == ["Hello", "World!!"]


def test_extract_ascii_strings_min_len_validation() -> None:
    with pytest.raises(ValueError, match="min_len"):
        ropper.extract_ascii_strings(b"abc", min_len=0)


def test_get_strings_reads_fixture_binary() -> None:
    result = ropper.get_strings(str(_FIXTURE_BINARY), min_len=4)
    assert result.total_found > 0
    assert result.returned == len(result.strings)


def test_get_strings_truncates() -> None:
    result = ropper.get_strings(str(_FIXTURE_BINARY), min_len=4, max_results=1)
    assert result.truncated is True
    assert result.returned == 1


def test_get_strings_missing_binary_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ropper.get_strings("/no/such/binary")


@pytest.mark.requires_ropper
def test_enumerate_gadgets_integration() -> None:
    result = ropper.enumerate_gadgets(str(_FIXTURE_BINARY))
    assert result.total_found > 0


@pytest.mark.requires_ropper
def test_search_gadget_integration() -> None:
    result = ropper.search_gadget(str(_FIXTURE_BINARY), "ret")
    assert result.returned == len(result.gadgets)
