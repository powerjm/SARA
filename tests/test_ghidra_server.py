"""Tests for the ghidra MCP server (pure list_strings + skipped integration)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.ghidra import server as ghidra

_FIXTURE_BINARY = Path(__file__).resolve().parent / "fixtures" / "binaries" / "sample_overflow"


def test_extract_ascii_strings_finds_known_strings() -> None:
    data = b"\x00\x01Hello World\x00\x00/bin/sh\x00\x02ab\x00deadbeef"
    found = ghidra.extract_ascii_strings(data, min_len=4)
    values = [s.value for s in found]
    assert "Hello World" in values
    assert "/bin/sh" in values
    assert "deadbeef" in values
    assert "ab" not in values  # below min_len


def test_extract_ascii_strings_records_offsets() -> None:
    data = b"\x00\x00ABCD\x00"
    found = ghidra.extract_ascii_strings(data, min_len=4)
    assert found == [ghidra.FoundString(offset=2, value="ABCD")]


def test_extract_ascii_strings_min_len_validation() -> None:
    with pytest.raises(ValueError, match="min_len"):
        ghidra.extract_ascii_strings(b"abcd", min_len=0)


def test_list_strings_reads_fixture_binary() -> None:
    result = ghidra.list_strings(str(_FIXTURE_BINARY), min_len=4)
    assert result.total_found > 0
    assert result.returned == len(result.strings)
    values = [s.value for s in result.strings]
    assert any("Hello World" in v for v in values)


def test_list_strings_truncates() -> None:
    result = ghidra.list_strings(str(_FIXTURE_BINARY), min_len=4, max_results=2)
    assert result.truncated is True
    assert result.returned == 2


def test_list_strings_to_dict() -> None:
    result = ghidra.list_strings(str(_FIXTURE_BINARY), min_len=4, max_results=1)
    payload = ghidra.strings_result_to_dict(result)
    assert payload["returned"] == 1
    assert "offset" in payload["strings"][0]


def test_list_strings_missing_binary_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ghidra.list_strings("/no/such/binary")


@pytest.mark.requires_ghidra
def test_decompile_function_integration() -> None:
    result = ghidra.decompile_function(str(_FIXTURE_BINARY), "main")
    assert "code" in result


@pytest.mark.requires_ghidra
def test_disassemble_function_integration() -> None:
    result = ghidra.disassemble_function(str(_FIXTURE_BINARY), "main")
    assert result["instructions"]
