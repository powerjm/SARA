"""
Tests that the committed test fixtures are valid ground truth.

Covers two things the rest of the suite depends on:

  * every `tests/fixtures/run_records/*.json` round-trips through the schema,
    and the set spans all four outcomes;
  * the committed `sample_overflow` ELF matches its pinned SHA-256, is a fixed
    (non-PIE) executable, and its documented exploit fires the success marker
    when run natively (skipped off linux/x86_64).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import sys
from pathlib import Path

import pytest

from harness.record import Outcome, RunRecord

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RUN_RECORDS = FIXTURES / "run_records"
BIN_DIR = FIXTURES / "binaries"
BINARY = BIN_DIR / "sample_overflow"
CHAIN_JSON = BIN_DIR / "chain.json"
SHA_FILE = BIN_DIR / "sample_overflow.sha256"
EXPLOIT = BIN_DIR / "exploit.py"

_RECORD_FILES = sorted(RUN_RECORDS.glob("*.json"))
_CAN_RUN_NATIVE = sys.platform == "linux" and platform.machine() == "x86_64"


def _binary_sha256() -> str:
    return hashlib.sha256(BINARY.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Run-record fixtures                                                         #
# --------------------------------------------------------------------------- #


def test_run_record_fixtures_exist() -> None:
    assert _RECORD_FILES, "no run-record fixtures found under tests/fixtures/run_records"


@pytest.mark.parametrize("path", _RECORD_FILES, ids=lambda p: p.name)
def test_run_record_fixture_roundtrips(path: Path) -> None:
    dumped = RunRecord.model_validate_json(path.read_text()).model_dump_json()
    # A second pass must be byte-stable.
    assert RunRecord.model_validate_json(dumped).model_dump_json() == dumped


def test_run_record_fixtures_cover_all_outcomes() -> None:
    outcomes = {RunRecord.model_validate_json(p.read_text()).outcome for p in _RECORD_FILES}
    assert outcomes == set(Outcome)


# --------------------------------------------------------------------------- #
# Binary fixture                                                              #
# --------------------------------------------------------------------------- #


def test_binary_exists() -> None:
    assert BINARY.is_file(), f"committed fixture binary missing: {BINARY}"


def test_binary_matches_pinned_sha256() -> None:
    expected = SHA_FILE.read_text().split()[0]
    assert _binary_sha256() == expected


def test_binary_is_non_pie_elf() -> None:
    """ET_EXEC (not ET_DYN): a fixed load base is why the documented addresses
    in chain.json are stable."""
    data = BINARY.read_bytes()
    assert data[:4] == b"\x7fELF"
    e_type = int.from_bytes(data[16:18], "little")
    assert e_type == 2  # ET_EXEC


def test_chain_json_is_consistent_with_binary() -> None:
    chain = json.loads(CHAIN_JSON.read_text())
    assert chain["sha256"] == _binary_sha256()
    assert chain["success_marker"] == "Hello World"
    # The documented chain references the two real gadgets plus win.
    addrs = set(chain["documented_gadget_addresses"])
    assert {g["address"] for g in chain["gadgets"]} <= addrs
    assert chain["symbols"]["win"] in addrs


@pytest.mark.skipif(
    not _CAN_RUN_NATIVE, reason="documented exploit executes the x86_64 ELF natively"
)
def test_documented_exploit_fires_success_marker() -> None:
    spec = importlib.util.spec_from_file_location("sample_exploit", EXPLOIT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    proc = module.run_exploit(BINARY)
    assert b"Hello World" in proc.stdout
    assert proc.returncode == 0
