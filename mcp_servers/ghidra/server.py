"""
ghidra MCP server (PyGhidra bridge, ADR 0004).

Ghidra is driven through **PyGhidra** (Ghidra's first-party CPython/JPype
interface), pinned to Ghidra 11.4.3 + JDK 21 (ADR 0004). The four
program-dependent tools (`disassemble_function`, `decompile_function`,
`list_imports`, `get_xrefs`) go through a `_GhidraSession` that opens and
analyses a binary **once** and reuses the open program across calls — running
headless analysis per call is prohibitively slow.

Two layers, mirroring `mcp_servers/ropgadget/server.py`:

1. Pure, SDK-free functions. `list_strings` is implemented as a dependency-free
   `strings`-style ASCII extractor over the file bytes (NOT through Ghidra), so
   it is unit-tested on CI without skip. The other four tools require a live
   PyGhidra session, imported lazily inside the analysis entry; PyGhidra/Ghidra
   are lab-host-only, so their integration tests skip (not fail) when absent.

2. A thin `_build_server()` / `serve()` MCP shell that imports the MCP SDK lazily
   inside the function so importing this module never needs the SDK.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server import Server

DEFAULT_MAX_RESULTS = 5_000
DEFAULT_MIN_STRING_LEN = 4


# ---------------------------------------------------------------------------
# Typed results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FoundString:
    """One extracted string with the offset it starts at."""

    offset: int  # byte offset into the file
    value: str


@dataclass(slots=True)
class StringsResult:
    """Result of `list_strings`."""

    binary_path: str
    total_found: int
    returned: int
    truncated: bool
    strings: list[FoundString]


@dataclass(frozen=True, slots=True)
class Import:
    """One imported symbol."""

    name: str
    library: str


@dataclass(frozen=True, slots=True)
class Xref:
    """One cross-reference to a target address."""

    from_address: str
    to_address: str
    ref_type: str


# ---------------------------------------------------------------------------
# Pure: list_strings (no Ghidra needed — CI-tested without skip)
# ---------------------------------------------------------------------------

_PRINTABLE = frozenset(range(0x20, 0x7F))


def extract_ascii_strings(data: bytes, min_len: int = DEFAULT_MIN_STRING_LEN) -> list[FoundString]:
    """Pure `strings`-style extractor: printable ASCII runs >= min_len.

    Returns each run with the byte offset at which it begins. This is the real
    implementation of `list_strings` — it deliberately does not call Ghidra, so
    the string-extraction tool is fully testable on CI.
    """
    if min_len < 1:
        raise ValueError(f"min_len must be >= 1, got {min_len}")
    results: list[FoundString] = []
    run = bytearray()
    start = 0
    for index, byte in enumerate(data):
        if byte in _PRINTABLE:
            if not run:
                start = index
            run.append(byte)
            continue
        if len(run) >= min_len:
            results.append(FoundString(offset=start, value=run.decode("ascii")))
        run.clear()
    if len(run) >= min_len:
        results.append(FoundString(offset=start, value=run.decode("ascii")))
    return results


def list_strings(
    binary_path: str,
    min_len: int = DEFAULT_MIN_STRING_LEN,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> StringsResult:
    """Extract printable ASCII strings from the binary (pure extractor)."""
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


# ---------------------------------------------------------------------------
# PyGhidra session: analyse-once / reuse-program (ADR 0004)
# ---------------------------------------------------------------------------


class _GhidraSession:
    """Opens and analyses a binary once via PyGhidra, reusing the open program.

    PyGhidra is imported lazily on first use; on a host without PyGhidra/Ghidra
    the import raises and the integration tests skip. `flat_api()` yields a
    FlatProgramAPI context manager bound to the analysed program.
    """

    def __init__(self, binary_path: str) -> None:
        bp = Path(binary_path)
        if not bp.is_file():
            raise FileNotFoundError(f"binary not found: {binary_path}")
        self.binary_path = str(bp)
        self._started = False

    def _ensure_started(self) -> Any:
        """Start the PyGhidra JVM once and return the pyghidra module."""
        import pyghidra  # lazy: absent on CI, present on the lab host

        if not self._started:
            if not pyghidra.started():
                pyghidra.start()
            self._started = True
        return pyghidra

    def flat_api(self) -> Any:
        """Return a PyGhidra `open_program` context manager for the binary.

        Used as ``with session.flat_api() as flat: ...`` — PyGhidra runs
        auto-analysis once when the program is opened and exposes a
        FlatProgramAPI for the queries the tool functions make.
        """
        pyghidra = self._ensure_started()
        return pyghidra.open_program(self.binary_path, analyze=True)


def disassemble_function(binary_path: str, name_or_addr: str) -> dict[str, Any]:
    """Disassemble a function (by name or address) through PyGhidra.

    Returns the function name, entry address, and the list of instruction lines.
    Requires a live Ghidra; integration-only.
    """
    session = _GhidraSession(binary_path)
    with session.flat_api() as flat:
        function = _resolve_function(flat, name_or_addr)
        listing = flat.getCurrentProgram().getListing()
        body = function.getBody()
        instructions: list[str] = []
        for instruction in listing.getInstructions(body, True):
            instructions.append(f"{instruction.getAddress()}: {instruction}")
        return {
            "binary_path": session.binary_path,
            "function": function.getName(),
            "entry": str(function.getEntryPoint()),
            "instructions": instructions,
        }


def decompile_function(binary_path: str, name_or_addr: str) -> dict[str, Any]:
    """Decompile a function (by name or address) through PyGhidra.

    Returns the decompiled C text. Requires a live Ghidra; integration-only.
    """
    from ghidra.app.decompiler import DecompInterface  # lazy: Ghidra-only

    session = _GhidraSession(binary_path)
    with session.flat_api() as flat:
        program = flat.getCurrentProgram()
        function = _resolve_function(flat, name_or_addr)
        decompiler = DecompInterface()
        decompiler.openProgram(program)
        try:
            result = decompiler.decompileFunction(function, 60, None)
            code = result.getDecompiledFunction().getC() if result.decompileCompleted() else ""
        finally:
            decompiler.dispose()
        return {
            "binary_path": session.binary_path,
            "function": function.getName(),
            "entry": str(function.getEntryPoint()),
            "code": code,
        }


def list_imports(binary_path: str) -> dict[str, Any]:
    """List imported symbols through PyGhidra. Requires a live Ghidra."""
    session = _GhidraSession(binary_path)
    with session.flat_api() as flat:
        program = flat.getCurrentProgram()
        symbol_table = program.getSymbolTable()
        imports: list[Import] = []
        for symbol in symbol_table.getExternalSymbols():
            library = symbol.getParentNamespace().getName()
            imports.append(Import(name=symbol.getName(), library=str(library)))
        return {
            "binary_path": session.binary_path,
            "imports": [asdict(i) for i in imports],
        }


def get_xrefs(binary_path: str, address: str) -> dict[str, Any]:
    """List cross-references to an address through PyGhidra. Requires a live Ghidra."""
    session = _GhidraSession(binary_path)
    with session.flat_api() as flat:
        program = flat.getCurrentProgram()
        target = flat.toAddr(address)
        reference_manager = program.getReferenceManager()
        xrefs: list[Xref] = []
        for reference in reference_manager.getReferencesTo(target):
            xrefs.append(
                Xref(
                    from_address=str(reference.getFromAddress()),
                    to_address=str(reference.getToAddress()),
                    ref_type=str(reference.getReferenceType()),
                )
            )
        return {
            "binary_path": session.binary_path,
            "address": str(target),
            "xrefs": [asdict(x) for x in xrefs],
        }


def _resolve_function(flat: Any, name_or_addr: str) -> Any:
    """Resolve a function by name, else by address, on an open program.

    Raises ValueError when no function matches.
    """
    token = name_or_addr.strip()
    function = flat.getFunction(token)
    if function is not None:
        return function
    try:
        addr = flat.toAddr(token)
    except Exception as exc:  # noqa: BLE001 - normalize Ghidra parse errors
        raise ValueError(f"could not resolve function {name_or_addr!r}: {exc}") from exc
    function = flat.getFunctionContaining(addr)
    if function is None:
        raise ValueError(f"no function found for {name_or_addr!r}")
    return function


def strings_result_to_dict(result: StringsResult) -> dict[str, Any]:
    """Plain-dict view of a StringsResult."""
    return {
        "binary_path": result.binary_path,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "strings": [asdict(s) for s in result.strings],
    }


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

DISASSEMBLE_FUNCTION_NAME = "disassemble_function"
DISASSEMBLE_FUNCTION_DESCRIPTION = (
    "Disassemble a function (by name or address) using Ghidra. Returns the "
    "function's instruction listing."
)
DISASSEMBLE_FUNCTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "name_or_addr"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "name_or_addr": {
            "type": "string",
            "description": "Function name or address.",
        },
    },
}

DECOMPILE_FUNCTION_NAME = "decompile_function"
DECOMPILE_FUNCTION_DESCRIPTION = (
    "Decompile a function (by name or address) to C using Ghidra's decompiler."
)
DECOMPILE_FUNCTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "name_or_addr"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "name_or_addr": {
            "type": "string",
            "description": "Function name or address.",
        },
    },
}

LIST_IMPORTS_NAME = "list_imports"
LIST_IMPORTS_DESCRIPTION = "List the binary's imported symbols (name + library) using Ghidra."
LIST_IMPORTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
    },
}

LIST_STRINGS_NAME = "list_strings"
LIST_STRINGS_DESCRIPTION = (
    "Extract printable ASCII strings (runs of >= min_len printable bytes) from "
    "the binary, each with its file offset. Truncated to max_results."
)
LIST_STRINGS_SCHEMA: dict[str, Any] = {
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
            "maximum": 50_000,
            "description": "Truncate the result set to this many strings.",
        },
    },
}

GET_XREFS_NAME = "get_xrefs"
GET_XREFS_DESCRIPTION = "List cross-references to an address (callers / data refs) using Ghidra."
GET_XREFS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "address"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "address": {
            "type": "string",
            "description": "Target address (hex like '0x401166').",
        },
    },
}


# ---------------------------------------------------------------------------
# MCP shell
# ---------------------------------------------------------------------------


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call by name and return its plain-dict result."""
    if name == LIST_STRINGS_NAME:
        kwargs: dict[str, Any] = {}
        if "min_len" in arguments:
            kwargs["min_len"] = int(arguments["min_len"])
        if "max_results" in arguments:
            kwargs["max_results"] = int(arguments["max_results"])
        return strings_result_to_dict(list_strings(arguments["binary_path"], **kwargs))
    if name == DISASSEMBLE_FUNCTION_NAME:
        return disassemble_function(arguments["binary_path"], arguments["name_or_addr"])
    if name == DECOMPILE_FUNCTION_NAME:
        return decompile_function(arguments["binary_path"], arguments["name_or_addr"])
    if name == LIST_IMPORTS_NAME:
        return list_imports(arguments["binary_path"])
    if name == GET_XREFS_NAME:
        return get_xrefs(arguments["binary_path"], arguments["address"])
    raise ValueError(f"unknown tool: {name}")


def _build_server() -> Server[Any]:
    """Construct the MCP server with the Ghidra tools registered.

    The MCP SDK is imported here, not at module top, so importing this module to
    use the pure `list_strings` extractor directly never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("ghidra")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=DISASSEMBLE_FUNCTION_NAME,
                description=DISASSEMBLE_FUNCTION_DESCRIPTION,
                inputSchema=DISASSEMBLE_FUNCTION_SCHEMA,
            ),
            Tool(
                name=DECOMPILE_FUNCTION_NAME,
                description=DECOMPILE_FUNCTION_DESCRIPTION,
                inputSchema=DECOMPILE_FUNCTION_SCHEMA,
            ),
            Tool(
                name=LIST_IMPORTS_NAME,
                description=LIST_IMPORTS_DESCRIPTION,
                inputSchema=LIST_IMPORTS_SCHEMA,
            ),
            Tool(
                name=LIST_STRINGS_NAME,
                description=LIST_STRINGS_DESCRIPTION,
                inputSchema=LIST_STRINGS_SCHEMA,
            ),
            Tool(
                name=GET_XREFS_NAME,
                description=GET_XREFS_DESCRIPTION,
                inputSchema=GET_XREFS_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _dispatch(name, arguments)

    return server


async def serve() -> None:
    """Run the Ghidra MCP server over stdio."""
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
    #   python -m mcp_servers.ghidra.server <binary>   (lists strings, no Ghidra)
    # Or launch the stdio server:
    #   python -m mcp_servers.ghidra.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] != "--serve":
        print(json.dumps(strings_result_to_dict(list_strings(sys.argv[1]))))
    else:
        asyncio.run(serve())


__all__ = [
    "DECOMPILE_FUNCTION_DESCRIPTION",
    "DECOMPILE_FUNCTION_NAME",
    "DECOMPILE_FUNCTION_SCHEMA",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MIN_STRING_LEN",
    "DISASSEMBLE_FUNCTION_DESCRIPTION",
    "DISASSEMBLE_FUNCTION_NAME",
    "DISASSEMBLE_FUNCTION_SCHEMA",
    "GET_XREFS_DESCRIPTION",
    "GET_XREFS_NAME",
    "GET_XREFS_SCHEMA",
    "LIST_IMPORTS_DESCRIPTION",
    "LIST_IMPORTS_NAME",
    "LIST_IMPORTS_SCHEMA",
    "LIST_STRINGS_DESCRIPTION",
    "LIST_STRINGS_NAME",
    "LIST_STRINGS_SCHEMA",
    "FoundString",
    "Import",
    "StringsResult",
    "Xref",
    "decompile_function",
    "disassemble_function",
    "extract_ascii_strings",
    "get_xrefs",
    "list_imports",
    "list_strings",
    "strings_result_to_dict",
]
