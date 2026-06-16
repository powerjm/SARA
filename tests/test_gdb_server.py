"""Tests for the gdb MCP server (inspect-only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_servers.gdb import server as gdb

_FIXTURE_BINARY = Path(__file__).resolve().parent / "fixtures" / "binaries" / "sample_overflow"


def test_run_rejected() -> None:
    with pytest.raises(gdb.GdbExecutionRejected):
        gdb.run_gdb_batch(str(_FIXTURE_BINARY), ["run"])


def test_start_rejected() -> None:
    with pytest.raises(gdb.GdbExecutionRejected):
        gdb.run_gdb_batch(str(_FIXTURE_BINARY), ["start"])


@pytest.mark.parametrize(
    "command",
    ["r", "continue", "c", "starti", "attach 1", "jump *0x401166", "call win()", "finish"],
)
def test_execution_commands_rejected(command: str) -> None:
    with pytest.raises(gdb.GdbExecutionRejected):
        gdb.run_gdb_batch(str(_FIXTURE_BINARY), ["info functions", command])


def test_execution_commands_set_is_frozen() -> None:
    assert isinstance(gdb.EXECUTION_COMMANDS, frozenset)
    assert "run" in gdb.EXECUTION_COMMANDS
    assert "start" in gdb.EXECUTION_COMMANDS


def test_inspect_commands_pass_policy_check() -> None:
    # reject_if_execution must not raise for purely static commands.
    gdb.reject_if_execution(["info functions", "disassemble main", "info file"])


def test_set_breakpoint_returns_plan() -> None:
    plan = gdb.set_breakpoint("0x401166")
    assert plan.location == "0x401166"
    assert plan.gdb_command == "break 0x401166"


def test_set_breakpoint_accepts_int() -> None:
    plan = gdb.set_breakpoint(0x401166)
    assert plan.location == "0x401166"
    assert plan.gdb_command == "break 0x401166"


def test_set_breakpoint_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        gdb.set_breakpoint("  ")


def test_run_gdb_batch_missing_binary_raises_after_policy() -> None:
    # Policy check passes (static command), then the missing binary is reported.
    with pytest.raises(FileNotFoundError):
        gdb.run_gdb_batch("/no/such/binary", ["info functions"])


@pytest.mark.requires_gdb
def test_inspect_state_integration() -> None:
    result = gdb.inspect_state(str(_FIXTURE_BINARY), focus="main")
    assert isinstance(result, gdb.GdbBatchResult)
    assert "disassemble main" in result.commands
    assert result.output


@pytest.mark.requires_gdb
def test_disassemble_integration() -> None:
    result = gdb.disassemble(str(_FIXTURE_BINARY), "main")
    assert result.output
