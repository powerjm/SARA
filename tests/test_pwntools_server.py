"""Tests for the pwntools MCP server (pure Python; never skipped)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from mcp_servers.pwntools import server as pwn

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "binaries"


def _load_fixture_exploit() -> object:
    """Load the corpus-truth exploit module by path (mirrors conftest)."""
    path = _FIXTURES / "exploit.py"
    spec = importlib.util.spec_from_file_location("sara_fixture_exploit_pwn", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_payload_round_trips_fixture_chain() -> None:
    chain_path = _FIXTURES / "chain.json"
    chain_spec = json.loads(chain_path.read_text(encoding="utf-8"))["chain"]

    result = pwn.build_payload(chain_spec, "amd64")

    exploit = _load_fixture_exploit()
    expected = exploit.build_payload(chain_path)  # type: ignore[attr-defined]
    assert result.payload == expected
    assert result.length == len(expected)


def test_result_to_dict_shape() -> None:
    result = pwn.build_payload([{"kind": "raw", "hex": "deadbeef"}])
    assert pwn.result_to_dict(result) == {"length": 4, "hex": "deadbeef"}


def test_build_payload_raw_and_padding() -> None:
    spec: list[dict[str, Any]] = [
        {"kind": "padding", "bytes": 4, "fill": "0x41"},
        {"kind": "raw", "hex": "cafe"},
    ]
    result = pwn.build_payload(spec)
    assert result.payload == b"AAAA" + bytes.fromhex("cafe")


def test_build_payload_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown chain step kind"):
        pwn.build_payload([{"kind": "bogus"}])


def test_pack_address_i386() -> None:
    assert pwn.pack_address("0x4011ad", "i386") == bytes.fromhex("ad114000")


def test_pack_address_amd64_and_alias() -> None:
    expected = bytes.fromhex("ad11400000000000")
    assert pwn.pack_address("0x4011ad", "amd64") == expected
    assert pwn.pack_address("0x4011ad", "x86_64") == expected


def test_pack_address_unknown_arch_raises() -> None:
    with pytest.raises(ValueError, match="unknown arch"):
        pwn.pack_address("0x4011ad", "arm64")


def test_generate_pattern_is_deterministic() -> None:
    first = pwn.generate_pattern(64)
    second = pwn.generate_pattern(64)
    assert first == second
    assert len(first) == 64
    assert first.startswith(b"aaaa")


def test_generate_pattern_windows_are_unique() -> None:
    pattern = pwn.generate_pattern(256)
    windows = {bytes(pattern[i : i + 4]) for i in range(len(pattern) - 3)}
    assert len(windows) == len(pattern) - 3


def test_pattern_offset_finds_known_offset() -> None:
    pattern = pwn.generate_pattern(128)
    sub = pattern[40:44]
    assert pwn.pattern_offset(sub, length=128) == 40


def test_pattern_offset_not_found_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        pwn.pattern_offset("ZZZZ", length=64)
