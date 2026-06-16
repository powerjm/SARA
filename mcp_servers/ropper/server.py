"""
ropper MCP server.

Two layers, mirroring `mcp_servers/ropgadget/server.py`:

1. Pure, SDK-free functions doing the real work. `parse_gadgets` turns the
   `ropper --file X --nocolor` stdout into typed Gadget records and is
   unit-tested on a canned output string. The tool functions
   (`enumerate_gadgets`, `search_gadget`, `get_strings`) shell out to the
   `ropper` CLI (constructed argv, no shell), parse, and truncate.

2. A thin `_build_server()` / `serve()` MCP shell that imports the MCP SDK lazily
   inside the function so importing this module never needs the SDK.

ropper complements ROPgadget (different filters, sometimes different gadgets);
it is a lab-host-only dependency, so the integration tests skip (not fail) when
`ropper` is absent.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server import Server

DEFAULT_MAX_RESULTS = 2_000
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MIN_STRING_LEN = 4

# Errors that mean "the ropper CLI failed to run", caught as one name so the
# except clause is never the parenthesized multi-type form (ruff-formatter bug).
_RUN_ERRORS = (subprocess.CalledProcessError,)


@dataclass(frozen=True, slots=True)
class Gadget:
    """One ropper gadget."""

    address: str  # canonical hex string, lowercase, "0x..." prefix
    instructions: str  # raw instruction text, semicolon-separated
    length: int  # number of instructions


# Permissive: matches "0xHEX: pop rdi; ret;" (ropper uses ": " then "; "-joined).
_GADGET_LINE = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s*:\s*(.+?)\s*$")


def _canonical_address(raw: str) -> str:
    """Lowercase hex address."""
    return raw.lower()


def parse_gadgets(stdout: str) -> list[Gadget]:
    """Parse `ropper --file X --nocolor` stdout into typed Gadget objects.

    Permissive: skips lines that do not match the "0xADDR: insns" shape (banner,
    blank lines, the "N gadgets found" footer), so banner/format drift between
    ropper versions does not crash the parser.
    """
    gadgets: list[Gadget] = []
    for line in stdout.splitlines():
        match = _GADGET_LINE.match(line)
        if not match:
            continue
        addr, insns = match.group(1), match.group(2)
        # ropper separates instructions with "; " and trails a final ";".
        parts = [part.strip() for part in insns.split(";")]
        length = len([part for part in parts if part])
        gadgets.append(
            Gadget(
                address=_canonical_address(addr),
                instructions=insns.strip(),
                length=length,
            )
        )
    return gadgets


@dataclass(slots=True)
class GadgetsResult:
    """Result of `enumerate_gadgets` / `search_gadget`."""

    binary_path: str
    total_found: int
    returned: int
    truncated: bool
    gadgets: list[Gadget]


@dataclass(slots=True)
class StringsResult:
    """Result of `get_strings`."""

    binary_path: str
    total_found: int
    returned: int
    truncated: bool
    strings: list[str]


def _run_ropper(args: list[str], *, timeout_seconds: int) -> str:
    """Shell out to ropper with the given args and return stdout.

    Raises FileNotFoundError (mapped to a clear RuntimeError) when ropper is not
    on PATH — the integration tests skip before reaching here.
    """
    cmd = ["ropper", *args]
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
            "ropper binary not found on PATH. Install with: pip install ropper"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ropper timed out after {timeout_seconds}s") from exc
    except _RUN_ERRORS as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"ropper exited with status {exc.returncode}: {stderr}") from exc
    return proc.stdout


def enumerate_gadgets(
    binary_path: str,
    filter: str | None = None,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> GadgetsResult:
    """Enumerate gadgets via `ropper --file X --nocolor`, optionally filtered.

    `filter`, when given, is passed to ropper's `--search` so the tool surfaces
    ropper's own (mnemonic-aware) filtering, which is the point of exposing it
    alongside ROPgadget.
    """
    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")
    args = ["--file", str(bp), "--nocolor"]
    if filter:
        args += ["--search", filter]
    stdout = _run_ropper(args, timeout_seconds=timeout_seconds)
    gadgets = parse_gadgets(stdout)
    return _truncate_gadgets(str(bp), gadgets, max_results)


def search_gadget(
    binary_path: str,
    pattern: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> GadgetsResult:
    """Search for gadgets matching a ropper search pattern (e.g. 'pop rdi; ret')."""
    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")
    args = ["--file", str(bp), "--nocolor", "--search", pattern]
    stdout = _run_ropper(args, timeout_seconds=timeout_seconds)
    gadgets = parse_gadgets(stdout)
    return _truncate_gadgets(str(bp), gadgets, max_results)


def _truncate_gadgets(binary_path: str, gadgets: list[Gadget], max_results: int) -> GadgetsResult:
    """Apply the max_results truncation and build a GadgetsResult."""
    total_found = len(gadgets)
    truncated = total_found > max_results
    if truncated:
        gadgets = gadgets[:max_results]
    return GadgetsResult(
        binary_path=binary_path,
        total_found=total_found,
        returned=len(gadgets),
        truncated=truncated,
        gadgets=gadgets,
    )


_PRINTABLE = bytes(range(0x20, 0x7F))


def extract_ascii_strings(data: bytes, min_len: int = DEFAULT_MIN_STRING_LEN) -> list[str]:
    """Pure `strings`-style extractor: printable ASCII runs >= min_len.

    Used so `get_strings` has a real, dependency-free implementation that does
    not need the ropper CLI at all.
    """
    if min_len < 1:
        raise ValueError(f"min_len must be >= 1, got {min_len}")
    results: list[str] = []
    run = bytearray()
    for byte in data:
        if byte in _PRINTABLE:
            run.append(byte)
            continue
        if len(run) >= min_len:
            results.append(run.decode("ascii"))
        run.clear()
    if len(run) >= min_len:
        results.append(run.decode("ascii"))
    return results


def get_strings(
    binary_path: str,
    *,
    min_len: int = DEFAULT_MIN_STRING_LEN,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> StringsResult:
    """Extract printable ASCII strings from the binary (pure extractor).

    Implemented as a dependency-free `strings` pass over the file bytes rather
    than through the ropper CLI, so it works without ropper installed.
    """
    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")
    strings = extract_ascii_strings(bp.read_bytes(), min_len)
    total_found = len(strings)
    truncated = total_found > max_results
    if truncated:
        strings = strings[:max_results]
    return StringsResult(
        binary_path=str(bp),
        total_found=total_found,
        returned=len(strings),
        truncated=truncated,
        strings=strings,
    )


def gadgets_result_to_dict(result: GadgetsResult) -> dict[str, Any]:
    """Plain-dict view of a GadgetsResult."""
    return {
        "binary_path": result.binary_path,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "gadgets": [asdict(g) for g in result.gadgets],
    }


def strings_result_to_dict(result: StringsResult) -> dict[str, Any]:
    """Plain-dict view of a StringsResult."""
    return {
        "binary_path": result.binary_path,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "strings": result.strings,
    }


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

ENUMERATE_GADGETS_NAME = "enumerate_gadgets"
ENUMERATE_GADGETS_DESCRIPTION = (
    "Enumerate ROP gadgets in a binary using ropper (complements ROPgadget; the "
    "filtering and discovered set can differ). Returns (address, instructions, "
    "length) records, truncated to max_results with truncated=true when exceeded. "
    "An optional filter is passed to ropper's --search."
)
ENUMERATE_GADGETS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "filter": {
            "type": "string",
            "description": "Optional ropper --search expression, e.g. 'pop rdi'.",
        },
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many gadgets.",
        },
    },
}

SEARCH_GADGET_NAME = "search_gadget"
SEARCH_GADGET_DESCRIPTION = (
    "Search for gadgets matching a ropper search pattern (e.g. 'pop rdi; ret' or "
    "'mov [%]'). Returns the matching gadgets, truncated to max_results."
)
SEARCH_GADGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "pattern"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "pattern": {
            "type": "string",
            "description": "ropper search pattern, e.g. 'pop rdi; ret'.",
        },
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many gadgets.",
        },
    },
}

GET_STRINGS_NAME = "get_strings"
GET_STRINGS_DESCRIPTION = (
    "Extract printable ASCII strings (runs of >= min_len printable bytes) from "
    "the binary. Truncated to max_results with truncated=true when exceeded."
)
GET_STRINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "min_len": {
            "type": "integer",
            "default": DEFAULT_MIN_STRING_LEN,
            "minimum": 1,
            "maximum": 256,
            "description": "Minimum run length to count as a string.",
        },
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many strings.",
        },
    },
}


# ---------------------------------------------------------------------------
# MCP shell
# ---------------------------------------------------------------------------


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call by name and return its plain-dict result."""
    if name == ENUMERATE_GADGETS_NAME:
        kwargs: dict[str, Any] = {}
        if "max_results" in arguments:
            kwargs["max_results"] = int(arguments["max_results"])
        return gadgets_result_to_dict(
            enumerate_gadgets(arguments["binary_path"], arguments.get("filter"), **kwargs)
        )
    if name == SEARCH_GADGET_NAME:
        kwargs2: dict[str, Any] = {}
        if "max_results" in arguments:
            kwargs2["max_results"] = int(arguments["max_results"])
        return gadgets_result_to_dict(
            search_gadget(arguments["binary_path"], arguments["pattern"], **kwargs2)
        )
    if name == GET_STRINGS_NAME:
        kwargs3: dict[str, Any] = {}
        if "min_len" in arguments:
            kwargs3["min_len"] = int(arguments["min_len"])
        if "max_results" in arguments:
            kwargs3["max_results"] = int(arguments["max_results"])
        return strings_result_to_dict(get_strings(arguments["binary_path"], **kwargs3))
    raise ValueError(f"unknown tool: {name}")


def _build_server() -> Server[Any]:
    """Construct the MCP server with the ropper tools registered.

    The MCP SDK is imported here, not at module top, so importing this module to
    use the pure parser/extractor directly never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("ropper")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=ENUMERATE_GADGETS_NAME,
                description=ENUMERATE_GADGETS_DESCRIPTION,
                inputSchema=ENUMERATE_GADGETS_SCHEMA,
            ),
            Tool(
                name=SEARCH_GADGET_NAME,
                description=SEARCH_GADGET_DESCRIPTION,
                inputSchema=SEARCH_GADGET_SCHEMA,
            ),
            Tool(
                name=GET_STRINGS_NAME,
                description=GET_STRINGS_DESCRIPTION,
                inputSchema=GET_STRINGS_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _dispatch(name, arguments)

    return server


async def serve() -> None:
    """Run the ropper MCP server over stdio."""
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
    #   python -m mcp_servers.ropper.server <binary> [filter]
    # Or launch the stdio server:
    #   python -m mcp_servers.ropper.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] != "--serve":
        flt = sys.argv[2] if len(sys.argv) > 2 else None
        out = enumerate_gadgets(sys.argv[1], flt)
        print(json.dumps(gadgets_result_to_dict(out)))
    else:
        asyncio.run(serve())


__all__ = [
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MIN_STRING_LEN",
    "DEFAULT_TIMEOUT_SECONDS",
    "ENUMERATE_GADGETS_DESCRIPTION",
    "ENUMERATE_GADGETS_NAME",
    "ENUMERATE_GADGETS_SCHEMA",
    "GET_STRINGS_DESCRIPTION",
    "GET_STRINGS_NAME",
    "GET_STRINGS_SCHEMA",
    "SEARCH_GADGET_DESCRIPTION",
    "SEARCH_GADGET_NAME",
    "SEARCH_GADGET_SCHEMA",
    "Gadget",
    "GadgetsResult",
    "StringsResult",
    "enumerate_gadgets",
    "extract_ascii_strings",
    "gadgets_result_to_dict",
    "get_strings",
    "parse_gadgets",
    "search_gadget",
    "strings_result_to_dict",
]
