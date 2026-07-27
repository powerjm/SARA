# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""
radare2 MCP server.

Two layers, mirroring `mcp_servers/ropgadget/server.py`:

1. Pure, SDK-free functions doing the real work. The parsing of radare2's JSON
   command output (`aflj`, `pdj`, `ij`) is split into standalone helpers
   (`parse_functions`, `parse_disasm`, `parse_analysis`) that take a JSON string
   and return typed dataclasses, so the parsing is unit-tested on canned JSON
   without radare2 installed. The tool functions open an `r2pipe` session
   (imported lazily inside the function), run the relevant `...j` command, and
   parse the result through those helpers.

2. A thin `_build_server()` / `serve()` MCP shell that imports the MCP SDK lazily
   inside the function so importing this module never needs the SDK.

`r2pipe` is a lab-host-only dependency; the integration tests skip (not fail)
when `r2` / `radare2` is absent.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server import Server

DEFAULT_MAX_RESULTS = 2_000
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_DISASM_COUNT = 16
DEFAULT_RECON_STRINGS = 60


# ---------------------------------------------------------------------------
# Typed results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Function:
    """One analyzed function (from `aflj`)."""

    name: str
    offset: int  # entry address
    size: int  # byte size


@dataclass(frozen=True, slots=True)
class Instruction:
    """One disassembled instruction (from `pdj`)."""

    offset: int
    opcode: str  # disassembled text
    bytes: str  # raw bytes, hex


@dataclass(frozen=True, slots=True)
class BinaryInfo:
    """High-level binary info (from `ij` / `iIj`)."""

    arch: str
    bits: int
    os: str
    binary_type: str
    canary: bool
    nx: bool
    pic: bool


# ---------------------------------------------------------------------------
# Pure parsers (unit-tested on canned JSON)
# ---------------------------------------------------------------------------


def _entry_address(entry: dict[str, Any]) -> int | None:
    """Address of an `aflj` / `pdj` / search-hit entry, or None if absent.

    radare2 **6.0 renamed the JSON address field `offset` -> `addr`** across
    `aflj`, `pdj`, and `/j`. Accept both so the parsers work on the 5.x line (the
    canned-JSON unit tests pin the `offset` schema) and on the 6.x line that
    Ubuntu 26.04 ships (which emits `addr`). Without this, the permissive parsers
    silently dropped *every* entry against a 6.x radare2 — analysis returned zero
    functions / instructions even though the tool ran fine.
    """
    value = entry.get("offset")
    if value is None:
        value = entry.get("addr")
    return None if value is None else int(value)


def parse_functions(json_str: str) -> list[Function]:
    """Parse `aflj` output into typed Function records.

    Permissive: skips entries that lack an address, so a radare2 version that
    adds/renames other fields does not crash the parser.
    """
    raw = json.loads(json_str) if json_str.strip() else []
    if not isinstance(raw, list):
        raise ValueError("aflj output is not a JSON array")
    functions: list[Function] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        offset = _entry_address(entry)
        if offset is None:
            continue
        functions.append(
            Function(
                name=str(entry.get("name", "")),
                offset=offset,
                size=int(entry.get("size", 0)),
            )
        )
    return functions


def parse_disasm(json_str: str) -> list[Instruction]:
    """Parse `pdj` output into typed Instruction records.

    `pdj` returns a JSON array of op dicts with `offset`, `opcode`/`disasm`, and
    `bytes`. Permissive about which disassembly-text key is present.
    """
    raw = json.loads(json_str) if json_str.strip() else []
    if not isinstance(raw, list):
        raise ValueError("pdj output is not a JSON array")
    instructions: list[Instruction] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        offset = _entry_address(entry)
        if offset is None:
            continue
        opcode = entry.get("disasm")
        if opcode is None:
            opcode = entry.get("opcode", "")
        instructions.append(
            Instruction(
                offset=offset,
                opcode=str(opcode),
                bytes=str(entry.get("bytes", "")),
            )
        )
    return instructions


def parse_analysis(json_str: str) -> BinaryInfo:
    """Parse `ij` / `iIj` output into a BinaryInfo summary.

    `ij` nests the info under a `"bin"` key; `iIj` returns the info object
    directly. Handles both shapes.
    """
    raw = json.loads(json_str) if json_str.strip() else {}
    if not isinstance(raw, dict):
        raise ValueError("info output is not a JSON object")
    info = raw.get("bin", raw)
    if not isinstance(info, dict):
        raise ValueError("info output missing 'bin' object")
    return BinaryInfo(
        arch=str(info.get("arch", "")),
        bits=int(info.get("bits", 0)),
        os=str(info.get("os", "")),
        binary_type=str(info.get("bintype", info.get("class", ""))),
        canary=bool(info.get("canary", False)),
        nx=bool(info.get("nx", False)),
        pic=bool(info.get("pic", False)),
    )


# --- recon parsers (ADR 0019): one-call target snapshot, canned-JSON tested ---


@dataclass(frozen=True, slots=True)
class ReconInfo:
    """The protection/architecture summary a `recon` call leads with."""

    arch: str
    bits: int
    endian: str
    os: str
    relro: str
    nx: bool
    pie: bool
    canary: bool


def parse_recon_info(json_str: str) -> ReconInfo:
    """Parse `iIj` (or `ij`'s `bin` object) into the checksec-style protections.

    Handles both the `iIj` shape (info object directly) and the `ij` shape (info
    nested under `bin`), reusing the same permissive approach as `parse_analysis`.
    `relro` is a string (`full`/`partial`/`no`) as radare2 reports it.
    """
    raw = json.loads(json_str) if json_str.strip() else {}
    if not isinstance(raw, dict):
        raise ValueError("info output is not a JSON object")
    info = raw.get("bin", raw)
    if not isinstance(info, dict):
        raise ValueError("info output missing 'bin' object")
    return ReconInfo(
        arch=str(info.get("arch", "")),
        bits=int(info.get("bits", 0)),
        endian=str(info.get("endian", "")),
        os=str(info.get("os", "")),
        relro=str(info.get("relro", "")),
        nx=bool(info.get("nx", False)),
        pie=bool(info.get("pic", info.get("pie", False))),
        canary=bool(info.get("canary", False)),
    )


def parse_entrypoint(json_str: str) -> int | None:
    """Parse `iej` (entrypoints) into the first entry vaddr, or None."""
    raw = json.loads(json_str) if json_str.strip() else []
    if not isinstance(raw, list):
        return None
    for entry in raw:
        if isinstance(entry, dict):
            value = entry.get("vaddr", entry.get("paddr"))
            if value is not None:
                return int(value)
    return None


def parse_imports(json_str: str) -> list[str]:
    """Parse `iij` (imports) into a de-duplicated, order-preserving name list."""
    raw = json.loads(json_str) if json_str.strip() else []
    if not isinstance(raw, list):
        raise ValueError("iij output is not a JSON array")
    names: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def parse_strings(json_str: str) -> list[dict[str, Any]]:
    """Parse `izj` / `izzj` (strings) into `{address, string}` rows.

    Accepts both the bare-list shape and the `{"strings": [...]}` wrapper; each row
    carries the string's vaddr (address) and text, permissive about missing keys.
    """
    raw = json.loads(json_str) if json_str.strip() else []
    entries = raw.get("strings", []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError("strings output is not a JSON array")
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = entry.get("string")
        if text is None:
            continue
        addr = entry.get("vaddr", entry.get("paddr"))
        rows.append({"address": int(addr) if addr is not None else None, "string": str(text)})
    return rows


def parse_writable_sections(json_str: str) -> list[dict[str, Any]]:
    """Parse `iSj` (sections) into the writable ones (`.bss`/`.data`/…).

    Keeps sections whose permission string contains `w`, returning `{name,
    address, size}` — the scratch space a store-gadget chain plants `/bin/sh` in.
    """
    raw = json.loads(json_str) if json_str.strip() else []
    if not isinstance(raw, list):
        raise ValueError("iSj output is not a JSON array")
    rows: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        perm = str(entry.get("perm", ""))
        if "w" not in perm.lower():
            continue
        addr = entry.get("vaddr", entry.get("paddr"))
        rows.append(
            {
                "name": str(entry.get("name", "")),
                "address": int(addr) if addr is not None else None,
                "size": int(entry.get("size", 0)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Tool functions (open an r2pipe session)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AnalyzeResult:
    """Result of `analyze_binary`."""

    binary_path: str
    info: BinaryInfo
    function_count: int


@dataclass(slots=True)
class FunctionsResult:
    """Result of `list_functions`."""

    binary_path: str
    total_found: int
    returned: int
    truncated: bool
    functions: list[Function]


@dataclass(slots=True)
class DisasmResult:
    """Result of `disassemble_at`."""

    binary_path: str
    address: int
    instructions: list[Instruction]


@dataclass(slots=True)
class SearchResult:
    """Result of `search_pattern`: addresses at which the pattern was found."""

    binary_path: str
    pattern: str
    total_found: int
    returned: int
    truncated: bool
    addresses: list[int]


# --- Per-run session cache (ADR 0019: the biggest radare2 speed win) --------
#
# Trial 2's `_open_session(analyze=True)` re-ran the slow `aaa` on EVERY
# analyze/list/disasm/search call — the same binary re-analyzed a dozen times a
# run. We now memoize one session per `(path, mtime)` and reuse it across every
# tool call in the run: `aaa` runs at most once, and the quiet-open flags fold in
# the log-hygiene fix (no `aaa` progress / reloc WARN / mouse-tracking escapes on
# stderr). `mtime` keys the cache so a rebuilt binary is re-opened, never stale.
# The opener is injectable (`_OPENER`) so the memoization is unit-testable in CI
# without r2pipe (which is a lab-host-only dependency).


@dataclass(slots=True)
class _CachedSession:
    """One memoized r2pipe session plus the state needed to reuse it safely."""

    session: Any
    mtime: float
    analyzed: bool


# path -> cached session. Process-global but scoped to one run in practice: the
# harness runs one binary at a time and calls `reset_session_cache()` between runs
# (there is no cross-run state to leak — the cache holds only open r2 handles).
_SESSION_CACHE: dict[str, _CachedSession] = {}

# Injectable opener for tests: `(binary_path) -> session`. None -> the real
# r2pipe opener with the quiet flags. A test sets this to a fake session factory
# and asserts the memoization (opener called once, `aaa` run once) without r2.
_OPENER: Callable[[str], Any] | None = None


def _default_opener(binary_path: str) -> Any:
    """Open a quiet r2pipe session (imported lazily; absent on CI)."""
    import r2pipe  # lazy: absent on CI, present on the lab host

    # `-2` sends r2's own stderr (aaa progress, reloc WARN) to /dev/null; the
    # scr.* settings drop ANSI colour and the interactive mouse-tracking escapes
    # that dominated the Trial-2 logs. Pure log hygiene: no effect on results.
    session = r2pipe.open(binary_path, flags=["-2"])
    session.cmd("e scr.color=0")
    session.cmd("e scr.interactive=false")
    return session


def reset_session_cache() -> None:
    """Quit and drop every cached session (call between runs / in test teardown)."""
    for cached in _SESSION_CACHE.values():
        # Best-effort cleanup — a session that never opened / already closed must
        # not raise on teardown.
        with contextlib.suppress(Exception):
            cached.session.quit()
    _SESSION_CACHE.clear()


def _open_session(binary_path: str, *, analyze: bool, timeout_seconds: int) -> Any:
    """Return a memoized r2pipe session for the binary, analyzing it at most once.

    Raises FileNotFoundError if the binary is missing; the r2pipe import failing
    (tool absent) propagates so the integration tests skip. The returned session
    is owned by the cache — callers must NOT quit it (that would close it for the
    next tool call); `reset_session_cache()` disposes of them.
    """
    bp = Path(binary_path)
    if not bp.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")
    key = str(bp)
    mtime = bp.stat().st_mtime
    cached = _SESSION_CACHE.get(key)
    if cached is None or cached.mtime != mtime:
        opener = _OPENER or _default_opener
        session = opener(key)
        session.cmd(f"e anal.timeout={timeout_seconds}")
        cached = _CachedSession(session=session, mtime=mtime, analyzed=False)
        _SESSION_CACHE[key] = cached
    if analyze and not cached.analyzed:
        cached.session.cmd("aaa")
        cached.analyzed = True
    return cached.session


def analyze_binary(
    binary_path: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> AnalyzeResult:
    """Run full analysis (`aaa`) and return a binary-info summary."""
    session = _open_session(binary_path, analyze=True, timeout_seconds=timeout_seconds)
    info = parse_analysis(session.cmd("ij"))
    functions = parse_functions(session.cmd("aflj"))
    return AnalyzeResult(
        binary_path=str(Path(binary_path)),
        info=info,
        function_count=len(functions),
    )


def list_functions(
    binary_path: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> FunctionsResult:
    """List analyzed functions, truncated to `max_results`."""
    session = _open_session(binary_path, analyze=True, timeout_seconds=timeout_seconds)
    functions = parse_functions(session.cmd("aflj"))
    total_found = len(functions)
    truncated = total_found > max_results
    if truncated:
        functions = functions[:max_results]
    return FunctionsResult(
        binary_path=str(Path(binary_path)),
        total_found=total_found,
        returned=len(functions),
        truncated=truncated,
        functions=functions,
    )


def disassemble_at(
    binary_path: str,
    address: int | str,
    count: int = DEFAULT_DISASM_COUNT,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> DisasmResult:
    """Disassemble `count` instructions starting at `address`."""
    addr = _coerce_int(address)
    session = _open_session(binary_path, analyze=False, timeout_seconds=timeout_seconds)
    instructions = parse_disasm(session.cmd(f"pdj {int(count)} @ {addr}"))
    return DisasmResult(
        binary_path=str(Path(binary_path)),
        address=addr,
        instructions=instructions,
    )


def search_pattern(
    binary_path: str,
    pattern: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> SearchResult:
    """Search for a hex/string pattern, returning the addresses it occurs at."""
    session = _open_session(binary_path, analyze=False, timeout_seconds=timeout_seconds)
    raw = session.cmd(f"/j {pattern}")
    hits = json.loads(raw) if raw.strip() else []
    addresses: list[int] = []
    if isinstance(hits, list):
        for hit in hits:
            if isinstance(hit, dict):
                addr = _entry_address(hit)
                if addr is not None:
                    addresses.append(addr)
    total_found = len(addresses)
    truncated = total_found > max_results
    if truncated:
        addresses = addresses[:max_results]
    return SearchResult(
        binary_path=str(Path(binary_path)),
        pattern=pattern,
        total_found=total_found,
        returned=len(addresses),
        truncated=truncated,
        addresses=addresses,
    )


def _coerce_int(raw: int | str) -> int:
    """Parse an int or a hex (0x-prefixed) / decimal string into an int."""
    if isinstance(raw, bool):
        raise ValueError(f"invalid integer value: {raw!r}")
    if isinstance(raw, int):
        return raw
    token = str(raw).strip()
    return int(token, 0)


@dataclass(slots=True)
class ReconResult:
    """One-call target snapshot (ADR 0019): the winning-trajectory recon step."""

    binary_path: str
    info: ReconInfo
    entrypoint: int | None
    functions: dict[str, int]  # name -> entry address
    imports: list[str]
    interesting_strings: list[dict[str, Any]]  # {address, string}
    writable_sections: list[dict[str, Any]]  # {name, address, size}


# Substrings that mark a string as exploitation-relevant, so recon surfaces them
# even when the string table is truncated to the first N rows (a `/bin/sh` buried
# past the cap would otherwise be missed — and finding it first is step 4a of the
# methodology). Case-insensitive.
_INTERESTING_STRING_MARKERS = ("/bin/sh", "/bin/bash", "sh", "system", "flag", "cat ")


def _select_interesting(strings: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """First `limit` strings, but always include any exploitation-relevant one."""
    head = strings[:limit]
    seen = {id(row) for row in head}
    for row in strings[limit:]:
        text = str(row.get("string", "")).lower()
        if any(marker in text for marker in _INTERESTING_STRING_MARKERS) and id(row) not in seen:
            head.append(row)
    return head


def recon(
    binary_path: str,
    *,
    max_strings: int = DEFAULT_RECON_STRINGS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ReconResult:
    """Snapshot a target in one call: arch/checksec, entry, functions, imports,
    interesting strings (incl. ``/bin/sh``), and writable segments.

    Replaces the 5+ round-trip ``analyze + list_functions + list_imports +
    list_strings + search_pattern`` opening sequence (ADR 0019) using the single
    cached analyzed session, so ``aaa`` runs once. Mechanically equivalent to
    ``rabin2 -I`` + ``checksec`` + ``nm`` + ``strings`` (capability-parity, ADR 0017).
    """
    session = _open_session(binary_path, analyze=True, timeout_seconds=timeout_seconds)
    info = parse_recon_info(session.cmd("iIj"))
    entrypoint = parse_entrypoint(session.cmd("iej"))
    functions = {f.name: f.offset for f in parse_functions(session.cmd("aflj"))}
    imports = parse_imports(session.cmd("iij"))
    strings = _select_interesting(parse_strings(session.cmd("izj")), max_strings)
    writable = parse_writable_sections(session.cmd("iSj"))
    return ReconResult(
        binary_path=str(Path(binary_path)),
        info=info,
        entrypoint=entrypoint,
        functions=functions,
        imports=imports,
        interesting_strings=strings,
        writable_sections=writable,
    )


def recon_result_to_dict(result: ReconResult) -> dict[str, Any]:
    """Terse plain-dict view of a ReconResult."""
    return {
        "binary_path": result.binary_path,
        "info": asdict(result.info),
        "entrypoint": result.entrypoint,
        "functions": result.functions,
        "imports": result.imports,
        "interesting_strings": result.interesting_strings,
        "writable_sections": result.writable_sections,
    }


# ---------------------------------------------------------------------------
# Plain-dict views
# ---------------------------------------------------------------------------


def analyze_result_to_dict(result: AnalyzeResult) -> dict[str, Any]:
    """Plain-dict view of an AnalyzeResult."""
    return {
        "binary_path": result.binary_path,
        "info": asdict(result.info),
        "function_count": result.function_count,
    }


def functions_result_to_dict(result: FunctionsResult) -> dict[str, Any]:
    """Plain-dict view of a FunctionsResult."""
    return {
        "binary_path": result.binary_path,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "functions": [asdict(f) for f in result.functions],
    }


def disasm_result_to_dict(result: DisasmResult) -> dict[str, Any]:
    """Plain-dict view of a DisasmResult."""
    return {
        "binary_path": result.binary_path,
        "address": result.address,
        "instructions": [asdict(i) for i in result.instructions],
    }


def search_result_to_dict(result: SearchResult) -> dict[str, Any]:
    """Plain-dict view of a SearchResult."""
    return {
        "binary_path": result.binary_path,
        "pattern": result.pattern,
        "total_found": result.total_found,
        "returned": result.returned,
        "truncated": result.truncated,
        "addresses": result.addresses,
    }


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

ANALYZE_BINARY_NAME = "analyze_binary"
ANALYZE_BINARY_DESCRIPTION = (
    "Run radare2 full analysis (aaa) on a binary and return a summary: "
    "architecture, bit width, OS, type, and the protection flags (canary, NX, "
    "PIC) plus the count of discovered functions."
)
ANALYZE_BINARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
    },
}

LIST_FUNCTIONS_NAME = "list_functions"
LIST_FUNCTIONS_DESCRIPTION = (
    "List the functions radare2 discovers (aflj), each with name, entry offset, "
    "and byte size. Truncated to max_results with truncated=true when exceeded."
)
LIST_FUNCTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many functions.",
        },
    },
}

DISASSEMBLE_AT_NAME = "disassemble_at"
DISASSEMBLE_AT_DESCRIPTION = (
    "Disassemble count instructions starting at an address (pdj). Returns each "
    "instruction's offset, opcode text, and raw bytes."
)
DISASSEMBLE_AT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "address"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "address": {
            "type": "string",
            "description": "Start address (hex like '0x401166' or decimal).",
        },
        "count": {
            "type": "integer",
            "default": DEFAULT_DISASM_COUNT,
            "minimum": 1,
            "maximum": 512,
            "description": "Number of instructions to disassemble.",
        },
    },
}

RECON_NAME = "recon"
RECON_DESCRIPTION = (
    "One-call target reconnaissance: architecture/bits/endianness, checksec "
    "(NX, PIE, RELRO, canary), entrypoint, the function table (name -> address), "
    "imports, exploitation-relevant strings (including /bin/sh if present), and "
    "writable segments (.bss/.data scratch). Start here — it replaces the "
    "analyze + list_functions + list_imports + list_strings opening sequence in a "
    "single call, and searches strings for you so you can point an argument "
    "register at /bin/sh when it already exists in the binary."
)
RECON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "max_strings": {
            "type": "integer",
            "default": DEFAULT_RECON_STRINGS,
            "minimum": 1,
            "maximum": 2_000,
            "description": "Cap on returned strings (relevant ones are kept beyond the cap).",
        },
    },
}

SEARCH_PATTERN_NAME = "search_pattern"
SEARCH_PATTERN_DESCRIPTION = (
    "Search the binary for a pattern (radare2 /j; a string, or hex with a 0x "
    "prefix). Returns the addresses where it occurs, truncated to max_results."
)
SEARCH_PATTERN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["binary_path", "pattern"],
    "additionalProperties": False,
    "properties": {
        "binary_path": {"type": "string", "description": "Path to the ELF binary."},
        "pattern": {
            "type": "string",
            "description": "Pattern to search for (string, or 0x-prefixed hex).",
        },
        "max_results": {
            "type": "integer",
            "default": DEFAULT_MAX_RESULTS,
            "minimum": 1,
            "maximum": 10_000,
            "description": "Truncate the result set to this many hits.",
        },
    },
}


# ---------------------------------------------------------------------------
# MCP shell
# ---------------------------------------------------------------------------


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call by name and return its plain-dict result."""
    if name == RECON_NAME:
        kwargs_recon: dict[str, Any] = {}
        if "max_strings" in arguments:
            kwargs_recon["max_strings"] = int(arguments["max_strings"])
        return recon_result_to_dict(recon(arguments["binary_path"], **kwargs_recon))
    if name == ANALYZE_BINARY_NAME:
        return analyze_result_to_dict(analyze_binary(arguments["binary_path"]))
    if name == LIST_FUNCTIONS_NAME:
        kwargs: dict[str, Any] = {}
        if "max_results" in arguments:
            kwargs["max_results"] = int(arguments["max_results"])
        return functions_result_to_dict(list_functions(arguments["binary_path"], **kwargs))
    if name == DISASSEMBLE_AT_NAME:
        count = int(arguments.get("count", DEFAULT_DISASM_COUNT))
        return disasm_result_to_dict(
            disassemble_at(arguments["binary_path"], arguments["address"], count)
        )
    if name == SEARCH_PATTERN_NAME:
        kwargs2: dict[str, Any] = {}
        if "max_results" in arguments:
            kwargs2["max_results"] = int(arguments["max_results"])
        return search_result_to_dict(
            search_pattern(arguments["binary_path"], arguments["pattern"], **kwargs2)
        )
    raise ValueError(f"unknown tool: {name}")


def _build_server() -> Server[Any]:
    """Construct the MCP server with the radare2 tools registered.

    The MCP SDK is imported here, not at module top, so importing this module to
    use the pure parsers directly never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("radare2")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=RECON_NAME,
                description=RECON_DESCRIPTION,
                inputSchema=RECON_SCHEMA,
            ),
            Tool(
                name=ANALYZE_BINARY_NAME,
                description=ANALYZE_BINARY_DESCRIPTION,
                inputSchema=ANALYZE_BINARY_SCHEMA,
            ),
            Tool(
                name=LIST_FUNCTIONS_NAME,
                description=LIST_FUNCTIONS_DESCRIPTION,
                inputSchema=LIST_FUNCTIONS_SCHEMA,
            ),
            Tool(
                name=DISASSEMBLE_AT_NAME,
                description=DISASSEMBLE_AT_DESCRIPTION,
                inputSchema=DISASSEMBLE_AT_SCHEMA,
            ),
            Tool(
                name=SEARCH_PATTERN_NAME,
                description=SEARCH_PATTERN_DESCRIPTION,
                inputSchema=SEARCH_PATTERN_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _dispatch(name, arguments)

    return server


async def serve() -> None:
    """Run the radare2 MCP server over stdio."""
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
    #   python -m mcp_servers.radare2.server <binary>
    # Or launch the stdio server:
    #   python -m mcp_servers.radare2.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] != "--serve":
        result = analyze_binary(sys.argv[1])
        print(json.dumps(analyze_result_to_dict(result)))
    else:
        asyncio.run(serve())


__all__ = [
    "ANALYZE_BINARY_DESCRIPTION",
    "ANALYZE_BINARY_NAME",
    "ANALYZE_BINARY_SCHEMA",
    "DEFAULT_DISASM_COUNT",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_RECON_STRINGS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DISASSEMBLE_AT_DESCRIPTION",
    "DISASSEMBLE_AT_NAME",
    "DISASSEMBLE_AT_SCHEMA",
    "LIST_FUNCTIONS_DESCRIPTION",
    "LIST_FUNCTIONS_NAME",
    "LIST_FUNCTIONS_SCHEMA",
    "RECON_DESCRIPTION",
    "RECON_NAME",
    "RECON_SCHEMA",
    "SEARCH_PATTERN_DESCRIPTION",
    "SEARCH_PATTERN_NAME",
    "SEARCH_PATTERN_SCHEMA",
    "AnalyzeResult",
    "BinaryInfo",
    "DisasmResult",
    "Function",
    "FunctionsResult",
    "Instruction",
    "ReconInfo",
    "ReconResult",
    "SearchResult",
    "analyze_binary",
    "analyze_result_to_dict",
    "disasm_result_to_dict",
    "disassemble_at",
    "functions_result_to_dict",
    "list_functions",
    "parse_analysis",
    "parse_disasm",
    "parse_entrypoint",
    "parse_functions",
    "parse_imports",
    "parse_recon_info",
    "parse_strings",
    "parse_writable_sections",
    "recon",
    "recon_result_to_dict",
    "reset_session_cache",
    "search_pattern",
    "search_result_to_dict",
]
