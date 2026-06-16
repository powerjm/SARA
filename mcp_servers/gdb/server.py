"""
gdb MCP server (inspect-only).

GDB is exposed to the agent in **inspect mode only**. Execution of candidate
payloads happens through the validator sandbox, never through this tool
(ADR 0002: the validator owns all payload execution). This server therefore
*rejects* any GDB command that would run or resume the inferior — `run`,
`start`, `continue`, `attach`, `jump`, `call`, etc. — and only allows static
inspection (disassembly, symbol/function listing, examining the file).

Two layers, mirroring `mcp_servers/ropgadget/server.py`:

1. Pure, SDK-free functions: `run_gdb_batch` builds and (for the integration
   path) shells out to `gdb --batch -nx -ex ...`, after enforcing the
   inspect-only policy by inspecting each command's leading token; the tool
   functions (`inspect_state`, `set_breakpoint`, `disassemble`) build safe
   command lists. `set_breakpoint` is purely a recorded plan — it never runs
   anything.

2. A thin `_build_server()` / `serve()` MCP shell that imports the MCP SDK lazily
   inside the function so importing this module never needs the SDK.

`gdb` is a lab-host-only dependency; the integration test skips (not fails) when
`gdb` is absent.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server import Server

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_OUTPUT_CHARS = 16_000

# The GDB commands that run or resume the inferior. The first token of any
# requested command is checked against this set; a match is rejected. Includes
# the common abbreviations GDB accepts (r, c, ...).
EXECUTION_COMMANDS: frozenset[str] = frozenset(
    {
        "run",
        "r",
        "start",
        "starti",
        "continue",
        "c",
        "attach",
        "jump",
        "call",
        "return",
        "signal",
        "finish",
    }
)


class GdbExecutionRejected(RuntimeError):
    """Raised when a requested GDB command would execute/resume the inferior.

    GDB is inspect-only here; execution is the validator's job (ADR 0002).
    """


@dataclass(slots=True)
class GdbBatchResult:
    """Result of a (static) `gdb --batch` invocation."""

    binary_path: str
    commands: list[str]
    output: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class BreakpointPlan:
    """A recorded breakpoint plan. Pure: nothing is executed."""

    location: str
    gdb_command: str


def _leading_token(command: str) -> str:
    """The first whitespace-delimited token of a GDB command, lowercased."""
    stripped = command.strip()
    if not stripped:
        return ""
    return stripped.split()[0].lower()


def reject_if_execution(commands: list[str]) -> None:
    """Raise GdbExecutionRejected if any command would run/resume the inferior."""
    for command in commands:
        token = _leading_token(command)
        if token in EXECUTION_COMMANDS:
            raise GdbExecutionRejected(
                f"command {command!r} would execute the inferior; GDB is "
                f"inspect-only (the validator owns execution, ADR 0002)"
            )


def run_gdb_batch(
    binary_path: str,
    commands: list[str],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> GdbBatchResult:
    """Run a list of static GDB commands under `gdb --batch -nx` and return output.

    Enforces the inspect-only policy *first*: if any command's leading token is in
    `EXECUTION_COMMANDS`, raises `GdbExecutionRejected` before invoking GDB at
    all. The shell-out is the integration path (skipped on CI where gdb is
    absent).
    """
    reject_if_execution(commands)

    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")

    cmd: list[str] = ["gdb", "--batch", "-nx"]
    for command in commands:
        cmd += ["-ex", command]
    cmd.append(str(bp))

    try:
        proc = subprocess.run(  # noqa: S603 - args are constructed, not shell
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gdb binary not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gdb timed out after {timeout_seconds}s for {binary_path}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"gdb exited with status {exc.returncode} for {binary_path}: {stderr}"
        ) from exc

    output = proc.stdout
    truncated = len(output) > max_output_chars
    if truncated:
        output = output[:max_output_chars]
    return GdbBatchResult(
        binary_path=str(bp),
        commands=list(commands),
        output=output,
        truncated=truncated,
    )


def inspect_state(
    binary_path: str,
    focus: str | None = None,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> GdbBatchResult:
    """Statically inspect a binary: file/function info, and disassembly of `focus`.

    Builds a fixed set of *inspection* commands (`info functions`, `info file`,
    and `disassemble focus` when a focus symbol/address is given). No command
    runs the inferior.
    """
    commands = ["info file", "info functions"]
    if focus:
        commands.append(f"disassemble {focus}")
    return run_gdb_batch(binary_path, commands, timeout_seconds=timeout_seconds)


def set_breakpoint(location: str | int) -> BreakpointPlan:
    """Record a breakpoint plan. Pure: it builds a `break` command, runs nothing.

    The agent uses this to declare *where* it would break; actually hitting the
    breakpoint requires execution, which only the validator performs.
    """
    loc = location if isinstance(location, str) else hex(location)
    loc = loc.strip()
    if not loc:
        raise ValueError("breakpoint location must be non-empty")
    return BreakpointPlan(location=loc, gdb_command=f"break {loc}")


def disassemble(
    binary_path: str,
    name_or_addr: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> GdbBatchResult:
    """Disassemble a function (by name) or an address range, statically."""
    target = name_or_addr.strip()
    if not target:
        raise ValueError("name_or_addr must be non-empty")
    return run_gdb_batch(binary_path, [f"disassemble {target}"], timeout_seconds=timeout_seconds)


def batch_result_to_dict(result: GdbBatchResult) -> dict[str, Any]:
    """Plain-dict view of a GdbBatchResult."""
    return {
        "binary_path": result.binary_path,
        "commands": result.commands,
        "output": result.output,
        "truncated": result.truncated,
    }


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

INSPECT_STATE_NAME = "inspect_state"
INSPECT_STATE_DESCRIPTION = (
    "Statically inspect a binary with GDB (inspect-only; no execution). Returns "
    "file info, the function list, and — when focus is given — the disassembly of "
    "that symbol or address. GDB never runs the program: execution is the "
    "validator's job."
)
INSPECT_STATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "focus": {
            "type": "string",
            "description": "Optional function name or address to disassemble.",
        },
    },
}

SET_BREAKPOINT_NAME = "set_breakpoint"
SET_BREAKPOINT_DESCRIPTION = (
    "Record a breakpoint plan at a location (function name or address). This is a "
    "plan only — it returns the GDB command that would set the breakpoint; nothing "
    "is executed (the validator owns execution)."
)
SET_BREAKPOINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["location"],
    "additionalProperties": False,
    "properties": {
        "location": {
            "type": "string",
            "description": "Breakpoint location: a function name or address.",
        },
    },
}

DISASSEMBLE_NAME = "disassemble"
DISASSEMBLE_DESCRIPTION = (
    "Disassemble a function (by name) or an address with GDB, statically. No execution occurs."
)
DISASSEMBLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "name_or_addr"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "name_or_addr": {
            "type": "string",
            "description": "Function name or address to disassemble.",
        },
    },
}


# ---------------------------------------------------------------------------
# MCP shell
# ---------------------------------------------------------------------------


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call by name and return its plain-dict result."""
    if name == INSPECT_STATE_NAME:
        return batch_result_to_dict(inspect_state(arguments["binary_path"], arguments.get("focus")))
    if name == SET_BREAKPOINT_NAME:
        return asdict(set_breakpoint(arguments["location"]))
    if name == DISASSEMBLE_NAME:
        return batch_result_to_dict(
            disassemble(arguments["binary_path"], arguments["name_or_addr"])
        )
    raise ValueError(f"unknown tool: {name}")


def _build_server() -> Server[Any]:
    """Construct the MCP server with the (inspect-only) GDB tools registered.

    The MCP SDK is imported here, not at module top, so importing this module to
    use the pure functions directly never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("gdb")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=INSPECT_STATE_NAME,
                description=INSPECT_STATE_DESCRIPTION,
                inputSchema=INSPECT_STATE_SCHEMA,
            ),
            Tool(
                name=SET_BREAKPOINT_NAME,
                description=SET_BREAKPOINT_DESCRIPTION,
                inputSchema=SET_BREAKPOINT_SCHEMA,
            ),
            Tool(
                name=DISASSEMBLE_NAME,
                description=DISASSEMBLE_DESCRIPTION,
                inputSchema=DISASSEMBLE_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _dispatch(name, arguments)

    return server


async def serve() -> None:
    """Run the GDB (inspect-only) MCP server over stdio."""
    from mcp.server.stdio import stdio_server

    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":  # pragma: no cover
    # Tiny CLI for ad-hoc testing without MCP:
    #   python -m mcp_servers.gdb.server <binary> [focus]
    # Or launch the stdio server:
    #   python -m mcp_servers.gdb.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] != "--serve":
        focus = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(batch_result_to_dict(inspect_state(sys.argv[1], focus))))
    else:
        asyncio.run(serve())


__all__ = [
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DISASSEMBLE_DESCRIPTION",
    "DISASSEMBLE_NAME",
    "DISASSEMBLE_SCHEMA",
    "EXECUTION_COMMANDS",
    "INSPECT_STATE_DESCRIPTION",
    "INSPECT_STATE_NAME",
    "INSPECT_STATE_SCHEMA",
    "SET_BREAKPOINT_DESCRIPTION",
    "SET_BREAKPOINT_NAME",
    "SET_BREAKPOINT_SCHEMA",
    "BreakpointPlan",
    "GdbBatchResult",
    "GdbExecutionRejected",
    "batch_result_to_dict",
    "disassemble",
    "inspect_state",
    "reject_if_execution",
    "run_gdb_batch",
    "set_breakpoint",
]
