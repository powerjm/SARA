"""
Agent tool layer.

Maps the agent's tool calls onto the MCP-backed tool functions. Two kinds of
tool are advertised to the backend:

* ``enumerate_gadgets`` — wraps ``mcp_servers.ropgadget``'s pure
  ``enumerate_gadgets`` function. Dispatched by the ``enumerate`` graph node,
  which turns the result into a ``ToolObservation`` the agent sees on its next
  reason round.
* ``submit_payload`` — the agent's terminal action: it hands over the assembled
  payload bytes (hex) plus the ordered chain addresses. This one is *not*
  dispatched here — the ``propose`` node materializes it into ``payload.bin``
  and the ``validate`` node executes it. The spec is advertised so the backend
  knows the action exists.

The whole layer is injectable: ``ToolLayer(enumerate_fn=...)`` lets a test swap
in a canned enumerator so the agent loop runs end-to-end without the ROPgadget
CLI (or any binary on disk). This mirrors the MCP-server split — the real work
sits behind a plain callable, and the orchestration around it stays testable.

Step 4 wires only ROPgadget; the remaining tools (Ghidra, radare2, Ropper,
pwntools, GDB) join this layer in Step 7 without changing its shape.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent.state import ToolObservation
from backends.base import ToolSpec
from mcp_servers.ropgadget import server as ropgadget

ENUMERATE_GADGETS = ropgadget.TOOL_NAME  # "enumerate_gadgets"
SUBMIT_PAYLOAD = "submit_payload"

# Discoverability catalog: tool-server name -> dotted path of the module whose
# `serve()` coroutine runs that server over stdio. The live agent loop dispatches
# only the ROPgadget enumerator + the terminal submit_payload (see `ToolLayer`),
# but the full per-tool MCP server set landed in Step 7; this maps each to its
# entry point for launching / wiring without changing `ToolLayer` dispatch.
TOOL_SERVERS: dict[str, str] = {
    "ropgadget": "mcp_servers.ropgadget.server",
    "radare2": "mcp_servers.radare2.server",
    "ropper": "mcp_servers.ropper.server",
    "pwntools": "mcp_servers.pwntools.server",
    "gdb": "mcp_servers.gdb.server",
    "ghidra": "mcp_servers.ghidra.server",
}

SUBMIT_PAYLOAD_DESCRIPTION = (
    "Commit a candidate exploit. Provide the fully assembled payload bytes as a "
    "hex string (payload_hex); these are fed to the target on stdin by the "
    "validator. Optionally provide chain_addresses — the ordered list of "
    "gadget/target addresses your chain executes (hex strings like '0x4011ad') "
    "— so the validator can fingerprint the chain and decide whether it matches "
    "the documented exploit. Calling this ends the run."
)

# JSON Schema for ``submit_payload`` arguments. A plain dict (no SDK types) so
# this module imports without the MCP/LLM SDKs.
SUBMIT_PAYLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["payload_hex"],
    "additionalProperties": False,
    "properties": {
        "payload_hex": {
            "type": "string",
            "description": "Hex-encoded payload bytes fed to the target on stdin.",
        },
        "chain_addresses": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Ordered gadget/target addresses used by the chain (hex strings, "
                "e.g. '0x4011ad'), for fingerprint matching against the "
                "documented exploit."
            ),
        },
    },
}

# A callable shaped like ``mcp_servers.ropgadget.server.enumerate_gadgets``.
GadgetEnumerator = Callable[..., ropgadget.EnumerateResult]


def _format_gadgets(result: ropgadget.EnumerateResult) -> str:
    """Render an ``EnumerateResult`` into the text the agent reads."""
    header = (
        f"ROP gadgets in {result.binary_path}: returned {result.returned} of "
        f"{result.total_found} (truncated={str(result.truncated).lower()})."
    )
    lines = [f"{g.address}: {g.instructions}" for g in result.gadgets]
    return "\n".join([header, *lines])


@dataclass
class ToolLayer:
    """Dispatches the agent's tool calls to the underlying tool functions.

    ``enumerate_fn`` defaults to the real ROPgadget wrapper; tests inject a
    canned callable. ``max_observation_chars`` bounds the text handed back to
    the agent (full tool output lives in the trace, not in the prompt).
    """

    enumerate_fn: GadgetEnumerator = ropgadget.enumerate_gadgets
    max_observation_chars: int = 8_000

    def specs(self) -> list[ToolSpec]:
        """The tool specs advertised to the backend on every reason round."""
        return [
            ToolSpec(
                name=ENUMERATE_GADGETS,
                description=ropgadget.TOOL_DESCRIPTION,
                input_schema=ropgadget.TOOL_INPUT_SCHEMA,
            ),
            ToolSpec(
                name=SUBMIT_PAYLOAD,
                description=SUBMIT_PAYLOAD_DESCRIPTION,
                input_schema=SUBMIT_PAYLOAD_SCHEMA,
            ),
        ]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolObservation:
        """Run one tool call and return its observation.

        A tool that raises (missing binary, bad arguments, ROPgadget absent) is
        captured into an error observation rather than propagated, so one bad
        tool call cannot abort the run — the agent gets to react to it.
        ``submit_payload`` is terminal and handled by the propose node, so
        dispatching it here is a programming error and raises.
        """
        if name == SUBMIT_PAYLOAD:
            raise ValueError("submit_payload is terminal; it is handled by the propose node")
        if name != ENUMERATE_GADGETS:
            return self._observation(name, arguments, f"ERROR: unknown tool {name!r}", 0.0)

        start = time.monotonic()
        try:
            result = self.enumerate_fn(**arguments)
        except Exception as exc:  # noqa: BLE001 - surface any tool failure to the agent
            return self._observation(
                name, arguments, f"ERROR: {type(exc).__name__}: {exc}", time.monotonic() - start
            )
        return self._observation(name, arguments, _format_gadgets(result), time.monotonic() - start)

    def _observation(
        self, name: str, arguments: dict[str, Any], output: str, elapsed: float
    ) -> ToolObservation:
        truncated = len(output) > self.max_observation_chars
        return ToolObservation(
            tool_name=name,
            arguments=dict(arguments),
            output=output[: self.max_observation_chars],
            truncated=truncated,
            elapsed_seconds=elapsed,
        )


def parse_chain_addresses(raw: Any) -> list[int] | None:
    """Coerce ``submit_payload``'s ``chain_addresses`` into ordered ints.

    Accepts hex strings (``"0x4011ad"`` / ``"4011ad"``), decimal strings, and
    ints. Returns ``None`` when nothing usable was supplied (the run can still
    succeed; it just won't fingerprint-match). Raises ``ValueError`` on a value
    that is present but unparseable, so a malformed submission is caught.
    """
    if not raw:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"chain_addresses must be a list, got {type(raw).__name__}")
    out: list[int] = []
    for item in raw:
        if isinstance(item, bool):  # bool is an int subclass; reject explicitly
            raise ValueError(f"invalid chain address: {item!r}")
        if isinstance(item, int):
            out.append(item)
        elif isinstance(item, str):
            out.append(_parse_address(item))
        else:
            raise ValueError(f"invalid chain address: {item!r}")
    return out


def _parse_address(text: str) -> int:
    """Parse a single address string: ``0x``-prefixed hex, else decimal, else hex.

    A bare token is read as decimal first (so ``"32"`` is 32), falling back to
    hex (so ``"4011ad"`` is ``0x4011ad``). Anything unparseable raises with a
    uniform message.
    """
    token = text.strip()
    if token.lower().startswith("0x"):
        try:
            return int(token, 16)
        except ValueError:
            raise ValueError(f"invalid chain address: {text!r}") from None
    for base in (10, 16):
        try:
            return int(token, base)
        except ValueError:
            continue
    raise ValueError(f"invalid chain address: {text!r}")


@dataclass
class ToolCall:
    """A normalized tool call extracted from an assistant message."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


def normalize_tool_call(raw: dict[str, Any]) -> ToolCall:
    """Normalize a provider tool-call dict to ``ToolCall``.

    Backends pass tool calls through verbatim; this tolerates the common shapes
    — ``input`` (Anthropic) or ``arguments`` (OpenAI-family) for the payload,
    and a missing id.
    """
    arguments = raw.get("input")
    if arguments is None:
        arguments = raw.get("arguments")
    return ToolCall(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        arguments=dict(arguments) if isinstance(arguments, dict) else {},
    )


__all__ = [
    "ENUMERATE_GADGETS",
    "SUBMIT_PAYLOAD",
    "SUBMIT_PAYLOAD_DESCRIPTION",
    "SUBMIT_PAYLOAD_SCHEMA",
    "TOOL_SERVERS",
    "GadgetEnumerator",
    "ToolCall",
    "ToolLayer",
    "normalize_tool_call",
    "parse_chain_addresses",
]
