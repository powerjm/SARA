"""
ROPgadget MCP server.

Two layers, deliberately split:

1. `enumerate_gadgets(...)` — a pure Python function that shells out to the
   `ROPgadget` CLI, parses its output via `parser.parse_gadgets`, and returns a
   typed `EnumerateResult`. It has no dependency on the MCP SDK, so the
   parsing / shell-out / truncation logic is unit-testable in isolation.

2. `serve()` — a thin MCP stdio server that exposes `enumerate_gadgets` as a
   single tool. `_build_server()` registers the handlers; `serve()` wires that
   server to stdio. The agent reaches the function through this layer at
   runtime.

The split is the worked example the rest of the tool layer copies: keep the
real work in an SDK-free function, and keep the MCP shell thin enough that the
evolving SDK API surface never touches the testable core (ADR rationale in
`docs/INFRASTRUCTURE_PLAN.md`).
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_servers.ropgadget.parser import Gadget, parse_gadgets

if TYPE_CHECKING:
    from mcp.server import Server

DEFAULT_MAX_RESULTS = 2_000
DEFAULT_TIMEOUT_SECONDS = 60

TOOL_NAME = "enumerate_gadgets"
TOOL_DESCRIPTION = (
    "Enumerate ROP gadgets in a binary using ROPgadget. Returns a list of "
    "(address, instructions, length) records. The output is deduplicated by "
    "default; set include_duplicates=true to surface every address at which an "
    "instruction sequence occurs (useful when a chain needs a gadget at a "
    "specific address). Large outputs are truncated to max_results, with "
    "truncated=true so the caller can re-query with a tighter filter."
)

# JSON Schema for the tool's arguments. A plain dict so this module imports
# without the MCP SDK; `_build_server()` hands it to `types.Tool`.
# `timeout_seconds` is deliberately omitted: the wall-clock cap is server
# policy, not something the agent may relax. `additionalProperties: false`
# enforces that.
TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {
            "type": "string",
            "description": "Path to the ELF binary to scan for gadgets.",
        },
        "filter_regex": {
            "type": "string",
            "description": (
                "Keep only gadgets whose instruction text matches this Python "
                "regex (re.search), e.g. 'pop rdi' or '^pop .* ; ret$'. Applied "
                "after enumeration, so total_found reflects the matches."
            ),
        },
        "max_length": {
            "type": "integer",
            "default": 6,
            "minimum": 1,
            "maximum": 20,
            "description": "Maximum number of instructions per gadget.",
        },
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many gadgets.",
        },
        "include_duplicates": {
            "type": "boolean",
            "default": False,
            "description": (
                "Pass --all to ROPgadget so every address of an otherwise "
                "duplicate gadget is reported, instead of one per unique "
                "instruction sequence."
            ),
        },
    },
}


@dataclass(slots=True)
class EnumerateResult:
    """Typed result from `enumerate_gadgets`."""

    binary_path: str
    total_found: int
    returned: int
    truncated: bool
    gadgets: list[Gadget]


def enumerate_gadgets(
    binary_path: str,
    filter_regex: str | None = None,
    max_length: int = 6,
    max_results: int = DEFAULT_MAX_RESULTS,
    include_duplicates: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> EnumerateResult:
    """Run ROPgadget against the binary and return parsed gadgets.

    `filter_regex`, when given, is a Python regex matched (via `re.search`)
    against each gadget's instruction text — applied here rather than through
    ROPgadget's mnemonic-oriented `--only`/`--filter` flags, so the semantics are
    exactly "keep gadgets whose disassembly matches", independent of ROPgadget's
    version-specific behaviour.

    Truncates to `max_results` and records whether truncation occurred so the
    agent can decide whether to re-query with a tighter filter. By default the
    output is ROPgadget's deduplicated view (one entry per unique instruction
    sequence); pass `include_duplicates=True` to map to `--all` and surface
    every address.
    """
    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")

    pattern: re.Pattern[str] | None = None
    if filter_regex:
        try:
            pattern = re.compile(filter_regex)
        except re.error as exc:
            raise ValueError(f"invalid filter_regex {filter_regex!r}: {exc}") from exc

    cmd: list[str] = [
        "ROPgadget",
        "--binary",
        str(bp),
        "--depth",
        str(max_length),
    ]
    if include_duplicates:
        cmd.append("--all")

    try:
        proc = subprocess.run(  # noqa: S603 - args are constructed, not shell
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ROPgadget binary not found on PATH. Install with: pip install ROPgadget"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ROPgadget timed out after {timeout_seconds}s for {binary_path}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"ROPgadget exited with status {exc.returncode} for {binary_path}: {stderr}"
        ) from exc

    gadgets = parse_gadgets(proc.stdout)
    if pattern is not None:
        gadgets = [g for g in gadgets if pattern.search(g.instructions)]
    total_found = len(gadgets)
    truncated = total_found > max_results
    if truncated:
        gadgets = gadgets[:max_results]

    return EnumerateResult(
        binary_path=str(bp),
        total_found=total_found,
        returned=len(gadgets),
        truncated=truncated,
        gadgets=gadgets,
    )


def result_to_dict(result: EnumerateResult) -> dict[str, Any]:
    """Plain-dict view of an `EnumerateResult` for JSON / MCP transport."""
    return {
        "binary_path": result.binary_path,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "gadgets": [asdict(g) for g in result.gadgets],
    }


def _serialize(result: EnumerateResult) -> str:
    """JSON string for the ad-hoc CLI path."""
    return json.dumps(result_to_dict(result))


def _build_server() -> Server[Any]:
    """Construct the MCP server with the `enumerate_gadgets` tool registered.

    The MCP SDK is imported here, not at module top, so importing this module
    (e.g. to use `enumerate_gadgets` directly in a test) never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("ropgadget")

    # The MCP SDK's registration decorators are themselves untyped; the handler
    # bodies below are fully typed.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=TOOL_NAME,
                description=TOOL_DESCRIPTION,
                inputSchema=TOOL_INPUT_SCHEMA,
            )
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != TOOL_NAME:
            raise ValueError(f"unknown tool: {name}")
        # Returning a dict makes the SDK populate both `structuredContent` and a
        # JSON text block, so callers get the typed payload and a human-readable
        # rendering. Validation against TOOL_INPUT_SCHEMA already ran.
        return result_to_dict(enumerate_gadgets(**arguments))

    return server


async def serve() -> None:
    """Run the ROPgadget MCP server over stdio."""
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
    #   python -m mcp_servers.ropgadget.server <binary> [filter]
    # Or launch the stdio server:
    #   python -m mcp_servers.ropgadget.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] != "--serve":
        target = sys.argv[1]
        flt = sys.argv[2] if len(sys.argv) > 2 else None
        out = enumerate_gadgets(target, filter_regex=flt)
        print(_serialize(out))
    else:
        asyncio.run(serve())


__all__ = [
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "TOOL_DESCRIPTION",
    "TOOL_INPUT_SCHEMA",
    "TOOL_NAME",
    "EnumerateResult",
    "Gadget",
    "enumerate_gadgets",
    "result_to_dict",
    "serve",
]
