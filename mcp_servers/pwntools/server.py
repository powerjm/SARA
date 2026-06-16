"""
pwntools MCP server.

Two layers, mirroring `mcp_servers/ropgadget/server.py`:

1. Pure, SDK-free functions doing the real work. Unlike the other tool servers
   this one has **no external dependency**: it reimplements the small slice of
   pwntools the agent needs (payload assembly, address packing, cyclic patterns)
   in plain Python, so it is fully unit-tested on CI and never skipped. We do not
   import `pwntools` — it is a lab-host-only native dependency, and the semantics
   we need (little-endian packing, De Bruijn `cyclic`, `pack` of a chain) are
   small and exactly specified.

2. A thin `_build_server()` / `serve()` MCP shell that imports the MCP SDK lazily
   inside the function so importing this module never needs the SDK.

The split is the worked example the rest of the tool layer copies (ADR rationale
in `docs/INFRASTRUCTURE_PLAN.md`).
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from typing import Any

DEFAULT_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
DEFAULT_SUBSEQUENCE = 4

# Bytes per address by architecture name. amd64 / x86_64 are aliases.
_ARCH_WIDTH: dict[str, int] = {
    "i386": 4,
    "amd64": 8,
    "x86_64": 8,
}

# ---------------------------------------------------------------------------
# Tool: build_payload
# ---------------------------------------------------------------------------

BUILD_PAYLOAD_NAME = "build_payload"
BUILD_PAYLOAD_DESCRIPTION = (
    "Assemble a ROP chain specification into raw payload bytes. chain_spec is an "
    "ordered list of step dicts: "
    "{'kind':'padding','bytes':N,'fill':'0x41'} emits N copies of the fill byte; "
    "{'kind':'gadget'|'target','address':'0x...'} and "
    "{'kind':'value','value':'0x...'} emit an 8-byte little-endian word; "
    "{'kind':'raw','hex':'deadbeef'} emits the decoded hex bytes verbatim. "
    "Returns the assembled length and hex. Unknown kinds raise an error."
)
BUILD_PAYLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["chain_spec"],
    "additionalProperties": False,
    "properties": {
        "chain_spec": {
            "type": "array",
            "description": "Ordered list of chain step dicts (see the tool description).",
            "items": {"type": "object"},
        },
        "arch": {
            "type": "string",
            "enum": ["i386", "amd64", "x86_64"],
            "default": "amd64",
            "description": "Architecture controlling address/value word width.",
        },
    },
}


@dataclass(slots=True)
class PayloadResult:
    """Typed result from `build_payload`."""

    length: int
    payload: bytes


def _word_width(arch: str) -> int:
    """Address width in bytes for an architecture name."""
    try:
        return _ARCH_WIDTH[arch]
    except KeyError:
        raise ValueError(f"unknown arch {arch!r}; known: {sorted(_ARCH_WIDTH)}") from None


def pack_address(addr: int | str, arch: str = "amd64") -> bytes:
    """Little-endian pack an address to the architecture's word width.

    `addr` may be an int or a hex/decimal string. `arch` is one of i386 (4
    bytes) or amd64 / x86_64 (8 bytes). Raises ValueError on an unknown arch.
    """
    width = _word_width(arch)
    value = _coerce_int(addr)
    fmt = "<I" if width == 4 else "<Q"
    try:
        return struct.pack(fmt, value)
    except struct.error as exc:
        raise ValueError(f"address {addr!r} does not fit in {width} bytes: {exc}") from exc


def _coerce_int(raw: int | str) -> int:
    """Parse an int or a hex (0x-prefixed) / decimal string into an int."""
    if isinstance(raw, bool):  # bool is an int subclass; reject explicitly
        raise ValueError(f"invalid integer value: {raw!r}")
    if isinstance(raw, int):
        return raw
    token = str(raw).strip()
    if token.lower().startswith("0x"):
        return int(token, 16)
    return int(token, 0)


def build_payload(chain_spec: list[dict[str, Any]], arch: str = "amd64") -> PayloadResult:
    """Assemble a chain specification into payload bytes.

    Each step contributes bytes by `kind`:
      padding -> `bytes` copies of the `fill` byte (a hex string like '0x41')
      gadget / target -> the address packed little-endian to the arch width
      value -> the literal value packed little-endian to the arch width
      raw -> the decoded `hex` bytes verbatim

    Raises ValueError on an unknown kind or a malformed step.
    """
    width = _word_width(arch)
    out = bytearray()
    for step in chain_spec:
        if not isinstance(step, dict):
            raise ValueError(f"malformed chain step (not a dict): {step!r}")
        kind = step.get("kind")
        if kind == "padding":
            fill = _coerce_int(step["fill"])
            if not 0 <= fill <= 0xFF:
                raise ValueError(f"padding fill {step['fill']!r} is not a byte value")
            out += bytes([fill]) * int(step["bytes"])
        elif kind in ("gadget", "target"):
            out += pack_address(step["address"], arch)
        elif kind == "value":
            out += _pack_value(step["value"], width)
        elif kind == "raw":
            out += bytes.fromhex(str(step["hex"]))
        else:
            raise ValueError(f"unknown chain step kind {kind!r}")
    return PayloadResult(length=len(out), payload=bytes(out))


def _pack_value(raw: int | str, width: int) -> bytes:
    """Little-endian pack a literal value to a given byte width."""
    value = _coerce_int(raw)
    fmt = "<I" if width == 4 else "<Q"
    try:
        return struct.pack(fmt, value)
    except struct.error as exc:
        raise ValueError(f"value {raw!r} does not fit in {width} bytes: {exc}") from exc


def result_to_dict(result: PayloadResult) -> dict[str, Any]:
    """Plain-dict view of a `PayloadResult` for JSON / MCP transport."""
    return {"length": result.length, "hex": result.payload.hex()}


# ---------------------------------------------------------------------------
# Tool: pack_address (exposed standalone too)
# ---------------------------------------------------------------------------

PACK_ADDRESS_NAME = "pack_address"
PACK_ADDRESS_DESCRIPTION = (
    "Little-endian pack a single address to the architecture word width "
    "(i386 -> 4 bytes, amd64/x86_64 -> 8 bytes). Returns the packed bytes as hex."
)
PACK_ADDRESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["address"],
    "additionalProperties": False,
    "properties": {
        "address": {
            "type": "string",
            "description": "Address to pack (hex string like '0x4011ad', or decimal).",
        },
        "arch": {
            "type": "string",
            "enum": ["i386", "amd64", "x86_64"],
            "default": "amd64",
            "description": "Architecture controlling the word width.",
        },
    },
}


# ---------------------------------------------------------------------------
# Tool: generate_pattern / pattern_offset (De Bruijn cyclic, pwntools-style)
# ---------------------------------------------------------------------------

GENERATE_PATTERN_NAME = "generate_pattern"
GENERATE_PATTERN_DESCRIPTION = (
    "Generate a cyclic De Bruijn pattern of the given length over a lowercase "
    "alphabet (default abc..z, subsequence length 4), like pwntools cyclic. "
    "Every 4-byte window is unique, so a crash value found in a register maps "
    "back to a single offset via pattern_offset."
)
GENERATE_PATTERN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["length"],
    "additionalProperties": False,
    "properties": {
        "length": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of bytes of pattern to generate.",
        },
    },
}

PATTERN_OFFSET_NAME = "pattern_offset"
PATTERN_OFFSET_DESCRIPTION = (
    "Find the byte offset of a 4-byte subsequence inside a cyclic pattern "
    "(the classic crash-offset finder). The subsequence is the value observed "
    "controlling the instruction pointer, given as ascii text or hex."
)
PATTERN_OFFSET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["subsequence"],
    "additionalProperties": False,
    "properties": {
        "subsequence": {
            "type": "string",
            "description": "The 4-byte subsequence to locate (ascii like 'aaja').",
        },
        "length": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": (
                "Pattern length to search within; 0 means search the canonical full-period pattern."
            ),
        },
    },
}


def _de_bruijn(alphabet: str, order: int) -> Any:
    """Yield a De Bruijn sequence B(k, n) over `alphabet` (k symbols, order n).

    Standard prefer-largest / FKM-based generator (the same construction
    pwntools' `cyclic` uses): every length-`order` window over the produced
    sequence is unique.
    """
    k = len(alphabet)
    a = [0] * (k * order)
    sequence: list[int] = []

    def db(t: int, p: int) -> None:
        if t > order:
            if order % p == 0:
                sequence.extend(a[1 : p + 1])
        else:
            a[t] = a[t - p]
            db(t + 1, p)
            for symbol in range(a[t - p] + 1, k):
                a[t] = symbol
                db(t + 1, t)

    db(1, 1)
    for index in sequence:
        yield alphabet[index]


def generate_pattern(
    length: int,
    alphabet: str = DEFAULT_ALPHABET,
    subsequence: int = DEFAULT_SUBSEQUENCE,
) -> bytes:
    """Build a cyclic pattern of `length` bytes (pwntools `cyclic`).

    Iterates the De Bruijn sequence B(len(alphabet), subsequence) and truncates
    to `length`. Deterministic for fixed inputs. Raises ValueError if the period
    is too short to satisfy `length`.
    """
    if length < 0:
        raise ValueError(f"length must be non-negative, got {length}")
    out = bytearray()
    for char in _de_bruijn(alphabet, subsequence):
        if len(out) >= length:
            break
        out += char.encode("ascii")
    if len(out) < length:
        raise ValueError(
            f"pattern period {len(out)} shorter than requested length {length}; "
            f"increase the alphabet or subsequence length"
        )
    return bytes(out[:length])


def pattern_offset(
    subsequence: bytes | str,
    length: int = 0,
    alphabet: str = DEFAULT_ALPHABET,
    sub_length: int = DEFAULT_SUBSEQUENCE,
) -> int:
    """Return the offset of `subsequence` within the cyclic pattern.

    `length` bounds the pattern searched; 0 searches the canonical full-period
    pattern. Raises ValueError if the subsequence is not found.
    """
    needle = subsequence.encode("ascii") if isinstance(subsequence, str) else bytes(subsequence)
    if length > 0:
        haystack = generate_pattern(length, alphabet, sub_length)
    else:
        haystack = bytes(char.encode("ascii") for char in _de_bruijn(alphabet, sub_length))
    index = haystack.find(needle)
    if index < 0:
        raise ValueError(f"subsequence {needle!r} not found in cyclic pattern")
    return index


# ---------------------------------------------------------------------------
# MCP shell
# ---------------------------------------------------------------------------


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call by name and return its plain-dict result."""
    if name == BUILD_PAYLOAD_NAME:
        arch = arguments.get("arch", "amd64")
        return result_to_dict(build_payload(arguments["chain_spec"], arch))
    if name == PACK_ADDRESS_NAME:
        arch = arguments.get("arch", "amd64")
        return {"hex": pack_address(arguments["address"], arch).hex()}
    if name == GENERATE_PATTERN_NAME:
        pattern = generate_pattern(int(arguments["length"]))
        return {"length": len(pattern), "hex": pattern.hex(), "ascii": pattern.decode("ascii")}
    if name == PATTERN_OFFSET_NAME:
        offset = pattern_offset(arguments["subsequence"], int(arguments.get("length", 0)))
        return {"offset": offset}
    raise ValueError(f"unknown tool: {name}")


def _build_server() -> Any:
    """Construct the MCP server with the pwntools tools registered.

    The MCP SDK is imported here, not at module top, so importing this module to
    use the pure functions directly never requires the SDK.
    """
    from mcp.server import Server
    from mcp.types import Tool

    server: Server[Any] = Server("pwntools")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=BUILD_PAYLOAD_NAME,
                description=BUILD_PAYLOAD_DESCRIPTION,
                inputSchema=BUILD_PAYLOAD_SCHEMA,
            ),
            Tool(
                name=PACK_ADDRESS_NAME,
                description=PACK_ADDRESS_DESCRIPTION,
                inputSchema=PACK_ADDRESS_SCHEMA,
            ),
            Tool(
                name=GENERATE_PATTERN_NAME,
                description=GENERATE_PATTERN_DESCRIPTION,
                inputSchema=GENERATE_PATTERN_SCHEMA,
            ),
            Tool(
                name=PATTERN_OFFSET_NAME,
                description=PATTERN_OFFSET_DESCRIPTION,
                inputSchema=PATTERN_OFFSET_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _dispatch(name, arguments)

    return server


async def serve() -> None:
    """Run the pwntools MCP server over stdio."""
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
    #   python -m mcp_servers.pwntools.server pattern <length>
    #   python -m mcp_servers.pwntools.server pack <addr> [arch]
    # Or launch the stdio server:
    #   python -m mcp_servers.pwntools.server --serve
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "pattern":
        print(generate_pattern(int(sys.argv[2])).decode("ascii"))
    elif len(sys.argv) >= 3 and sys.argv[1] == "pack":
        arch = sys.argv[3] if len(sys.argv) > 3 else "amd64"
        print(pack_address(sys.argv[2], arch).hex())
    else:
        asyncio.run(serve())


__all__ = [
    "BUILD_PAYLOAD_DESCRIPTION",
    "BUILD_PAYLOAD_NAME",
    "BUILD_PAYLOAD_SCHEMA",
    "DEFAULT_ALPHABET",
    "DEFAULT_SUBSEQUENCE",
    "GENERATE_PATTERN_DESCRIPTION",
    "GENERATE_PATTERN_NAME",
    "GENERATE_PATTERN_SCHEMA",
    "PACK_ADDRESS_DESCRIPTION",
    "PACK_ADDRESS_NAME",
    "PACK_ADDRESS_SCHEMA",
    "PATTERN_OFFSET_DESCRIPTION",
    "PATTERN_OFFSET_NAME",
    "PATTERN_OFFSET_SCHEMA",
    "PayloadResult",
    "build_payload",
    "generate_pattern",
    "pack_address",
    "pattern_offset",
    "result_to_dict",
    "serve",
]
