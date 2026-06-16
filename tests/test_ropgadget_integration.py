"""Integration tests for the ROPgadget MCP server (Step 2).

Two surfaces are exercised:

* `enumerate_gadgets(...)` — the SDK-free core, run against the real
  `sample_overflow` fixture binary. These assert the documented exploit's
  gadgets are discoverable and that truncation behaves.
* the MCP layer — driven both through the in-memory transport (fast, used for
  the protocol round-trip) and through a real stdio subprocess launched via
  `python -m mcp_servers.ropgadget.server --serve`.

Anything that shells out to ROPgadget is marked `requires_ropgadget` and skips
(does not fail) when the CLI is absent — see `tests/conftest.py`. The pure
schema / `list_tools` checks need no CLI and always run.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from mcp_servers.ropgadget.server import (
    TOOL_INPUT_SCHEMA,
    TOOL_NAME,
    EnumerateResult,
    _build_server,
    enumerate_gadgets,
    result_to_dict,
)

_CHAIN_JSON = Path(__file__).resolve().parent / "fixtures" / "binaries" / "chain.json"

# Generous ceiling so a wedged subprocess fails loudly instead of hanging CI.
_STDIO_TIMEOUT_SECONDS = 30


def _documented_gadgets() -> list[dict[str, str]]:
    """The exploit's ROP gadgets, from chain.json (the source of truth)."""
    data = json.loads(_CHAIN_JSON.read_text())
    gadgets: list[dict[str, str]] = data["gadgets"]
    return gadgets


def _addr_to_int(address: str) -> int:
    """Normalize a hex address string (zero-padded or not) to an int."""
    return int(address, 16)


# --------------------------------------------------------------------------- #
# enumerate_gadgets — the SDK-free core
# --------------------------------------------------------------------------- #


@pytest.mark.requires_ropgadget
def test_enumerate_finds_documented_gadgets(sample_overflow_path: Path) -> None:
    """Every gadget the documented exploit uses is discoverable by address+asm.

    `include_duplicates=True` (ROPgadget's --all) is required because the
    alignment `ret` at 0x4011ae is a duplicate of an earlier `ret` and is
    otherwise collapsed away by ROPgadget's default dedup.
    """
    result = enumerate_gadgets(str(sample_overflow_path), include_duplicates=True)

    by_addr = {_addr_to_int(g.address): g for g in result.gadgets}
    for documented in _documented_gadgets():
        addr = _addr_to_int(documented["address"])
        assert addr in by_addr, f"documented gadget {documented['address']} not enumerated"
        assert by_addr[addr].instructions == documented["asm"], (
            f"gadget at {documented['address']} disassembled as "
            f"{by_addr[addr].instructions!r}, expected {documented['asm']!r}"
        )


@pytest.mark.requires_ropgadget
def test_enumerate_default_dedup_finds_key_gadgets(sample_overflow_path: Path) -> None:
    """Even without --all, the unique `pop rdi ; ret` and a `ret` are present."""
    result = enumerate_gadgets(str(sample_overflow_path))

    instructions = {g.instructions for g in result.gadgets}
    assert "pop rdi ; ret" in instructions
    assert "ret" in instructions
    assert not result.truncated
    assert result.returned == result.total_found


@pytest.mark.requires_ropgadget
def test_enumerate_filter_regex_narrows_results(sample_overflow_path: Path) -> None:
    """`filter_regex` keeps only matching gadgets, including the pop-rdi gadget."""
    result = enumerate_gadgets(str(sample_overflow_path), filter_regex="pop rdi")

    assert result.total_found >= 1
    assert all("pop rdi" in g.instructions for g in result.gadgets)
    assert any(_addr_to_int(g.address) == 0x4011AD for g in result.gadgets)


@pytest.mark.requires_ropgadget
def test_enumerate_truncates_past_max_results(sample_overflow_path: Path) -> None:
    """Past `max_results`, the result set is capped and `truncated` is set."""
    full = enumerate_gadgets(str(sample_overflow_path))
    assert full.total_found > 5, "fixture should yield more than 5 gadgets"

    capped = enumerate_gadgets(str(sample_overflow_path), max_results=5)
    assert capped.truncated is True
    assert capped.returned == 5
    assert len(capped.gadgets) == 5
    assert capped.total_found == full.total_found


def test_enumerate_missing_binary_raises() -> None:
    """A nonexistent path fails fast, before any shell-out (no CLI needed)."""
    with pytest.raises(FileNotFoundError):
        enumerate_gadgets("/nonexistent/path/to/binary")


def test_result_to_dict_round_trips() -> None:
    """`result_to_dict` produces a JSON-serializable EnumerateResult view."""
    from mcp_servers.ropgadget.parser import Gadget

    result = EnumerateResult(
        binary_path="/bin/true",
        total_found=1,
        returned=1,
        truncated=False,
        gadgets=[Gadget(address="0x401000", instructions="ret", length=1)],
    )
    payload = result_to_dict(result)
    assert json.loads(json.dumps(payload)) == payload
    assert payload["gadgets"][0] == {
        "address": "0x401000",
        "instructions": "ret",
        "length": 1,
    }


# --------------------------------------------------------------------------- #
# MCP layer — in-memory transport (fast protocol round-trip)
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def _in_memory_client() -> AsyncIterator[Any]:
    """A ClientSession connected to the ropgadget server over in-memory streams.

    The helper performs the MCP `initialize` handshake before yielding.
    """
    from mcp.shared.memory import create_connected_server_and_client_session

    server = _build_server()
    async with create_connected_server_and_client_session(server) as client:
        yield client


async def test_mcp_list_tools_returns_enumerate_gadgets() -> None:
    """list_tools advertises exactly the enumerate_gadgets tool (no CLI needed)."""
    async with _in_memory_client() as client:
        listed = await client.list_tools()

    names = [tool.name for tool in listed.tools]
    assert names == [TOOL_NAME]

    tool = listed.tools[0]
    assert tool.description
    assert tool.inputSchema == TOOL_INPUT_SCHEMA
    assert tool.inputSchema["required"] == ["binary_path"]


@pytest.mark.requires_ropgadget
async def test_mcp_call_tool_returns_enumerate_result(sample_overflow_path: Path) -> None:
    """call_tool returns a payload matching EnumerateResult, via structuredContent."""
    async with _in_memory_client() as client:
        result = await client.call_tool(TOOL_NAME, {"binary_path": str(sample_overflow_path)})

    assert result.isError is False
    structured = result.structuredContent
    assert structured is not None
    assert set(structured) == {
        "binary_path",
        "total_found",
        "returned",
        "truncated",
        "gadgets",
    }
    assert structured["returned"] == len(structured["gadgets"])
    assert any(g["instructions"] == "pop rdi ; ret" for g in structured["gadgets"])

    # The same data is mirrored as a JSON text block for human/agent reading.
    assert result.content and result.content[0].type == "text"
    assert json.loads(result.content[0].text) == structured


async def test_mcp_call_tool_unknown_name_is_error() -> None:
    """An unknown tool name comes back as an MCP error result (no CLI needed)."""
    async with _in_memory_client() as client:
        result = await client.call_tool("not_a_tool", {"binary_path": "/bin/true"})
    assert result.isError is True


# --------------------------------------------------------------------------- #
# MCP layer — real stdio subprocess launch
# --------------------------------------------------------------------------- #


def _stdio_params() -> Any:
    """StdioServerParameters launching `python -m ...server --serve`.

    The child inherits the full environment (so $PATH still resolves ROPgadget)
    with PYTHONPATH pointing at the project root and PYTHONWARNINGS cleared, so
    a host-level `PYTHONWARNINGS=error` can't turn runpy's benign double-import
    RuntimeWarning into a startup crash.
    """
    from mcp import StdioServerParameters

    project_root = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": project_root}
    env.pop("PYTHONWARNINGS", None)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.ropgadget.server", "--serve"],
        env=env,
        cwd=project_root,
    )


@asynccontextmanager
async def _stdio_client() -> AsyncIterator[Any]:
    """A ClientSession connected to a freshly-launched stdio server subprocess."""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with (
        stdio_client(_stdio_params()) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def test_stdio_server_launches_and_lists_tools() -> None:
    """The documented `--serve` entrypoint starts and answers list_tools."""

    async def _run() -> list[str]:
        async with _stdio_client() as session:
            listed = await session.list_tools()
            return [tool.name for tool in listed.tools]

    names = await asyncio.wait_for(_run(), timeout=_STDIO_TIMEOUT_SECONDS)
    assert names == [TOOL_NAME]


@pytest.mark.requires_ropgadget
async def test_stdio_server_call_tool_enumerates(sample_overflow_path: Path) -> None:
    """Over real stdio, call_tool enumerates gadgets from the fixture binary."""

    async def _run() -> dict[str, Any]:
        async with _stdio_client() as session:
            result = await session.call_tool(TOOL_NAME, {"binary_path": str(sample_overflow_path)})
            assert result.isError is False
            assert result.structuredContent is not None
            structured: dict[str, Any] = result.structuredContent
            return structured

    structured = await asyncio.wait_for(_run(), timeout=_STDIO_TIMEOUT_SECONDS)
    assert structured["returned"] >= 1
    assert any(g["instructions"] == "pop rdi ; ret" for g in structured["gadgets"])
