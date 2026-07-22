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

import json
import re
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


# --------------------------------------------------------------------------- #
# Text-format action parsing (ADR 0010)                                       #
# --------------------------------------------------------------------------- #
#
# The reasoning strategies instruct the model to write its action as text —
# react: ``Action: enumerate_gadgets({...})``; chain_of_thought: ``ACTION:
# submit_payload({...})``. The graph dispatches only *native* structured tool
# calls, so without this a literal-text action is ignored and the run gives up
# despite the model correctly intending a call. ``parse_text_actions`` bridges
# the two: when a reason turn carries no native tool call, the harness parses
# these lines into native-shaped call dicts. Native tool calls always win — this
# is a fallback, wired in ``agent.graph.node_reason``.

# ``\baction`` (word boundary) so "reaction:" / "transaction:" don't match; a
# known tool name must follow and be immediately invoked ("name("), which a
# prose mention of the tool is not. Case-insensitive to accept ACTION:/Action:.
_TEXT_ACTION_RE = re.compile(
    r"\baction[ \t]*:[ \t]*([A-Za-z_]\w*)[ \t]*(?=\()",
    re.IGNORECASE,
)


def parse_text_actions(text: str | None) -> list[dict[str, Any]]:
    """Extract text-format tool calls as native-shaped call dicts.

    Open models that don't emit native tool calls express them in a few text
    shapes; this recognizes the two seen in the wild:

    * an ``Action:`` / ``ACTION:`` line — ``Action: enumerate_gadgets({...})``
      (react / chain_of_thought), and
    * a JSON object — ``{"name": "enumerate_gadgets", "arguments": {...}}`` (often
      inside a ```` ```json ```` fence), which some instruct/uncensored models
      emit instead of a native call.

    Returns one dict per recognized call, in document order, each shaped like a
    native tool call (``{"id", "name", "arguments"}``) so the rest of the graph —
    ``route_after_reason``, ``node_enumerate``, ``_find_submit_call`` — treats it
    identically to a provider-emitted call. Only the two known tools are
    recognized; an unparseable argument blob yields empty ``arguments`` (the tool
    layer then surfaces the error to the agent). Returns ``[]`` when nothing
    matches.
    """
    if not text:
        return []
    known = {ENUMERATE_GADGETS, SUBMIT_PAYLOAD}
    calls: list[dict[str, Any]] = []

    # Form 1: `Action: name(args)`.
    for match in _TEXT_ACTION_RE.finditer(text):
        name = match.group(1)
        if name not in known:
            continue
        # The lookahead leaves match.end() on the "(" without consuming it.
        inner = _extract_paren_group(text, match.end())
        if inner is None:
            continue
        calls.append(
            {
                "id": f"text-action-{len(calls)}",
                "name": name,
                "arguments": _decode_action_args(inner),
            }
        )

    # Form 2: a JSON object `{"name": <known tool>, "arguments"|"input"|"parameters": {...}}`.
    for obj in _iter_json_objects(text):
        name = obj.get("name")
        if name not in known:
            continue
        args = obj.get("arguments")
        if args is None:
            args = obj.get("input")
        if args is None:
            args = obj.get("parameters")
        calls.append(
            {
                "id": f"text-action-{len(calls)}",
                "name": name,
                "arguments": args if isinstance(args, dict) else {},
            }
        )

    return calls


def _extract_paren_group(text: str, open_index: int) -> str | None:
    """Return the substring inside the parens opening at ``open_index``.

    Nesting- and quote-aware (single/double quotes with backslash escapes), so a
    ``(`` or ``)`` inside a string literal or a nested call does not close the
    group early. Returns ``None`` if the group is never balanced.
    """
    if open_index >= len(text) or text[open_index] != "(":
        return None
    depth = 0
    in_string = False
    quote = ""
    escaped = False
    for j in range(open_index, len(text)):
        ch = text[j]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : j]
    return None


def _decode_action_args(inner: str) -> dict[str, Any]:
    """Decode a text action's argument blob into a dict.

    The observed shape is a JSON object (``{"binary_path": "..."}``); trailing
    prose after the object is tolerated via ``raw_decode``. An empty blob or one
    that is not a JSON object yields ``{}`` — a benign miss the tool layer reports
    back to the agent, not a crash.
    """
    blob = inner.strip()
    if not blob:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(blob)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_brace_group(text: str, open_index: int) -> str | None:
    """Return the balanced ``{...}`` substring (incl. braces) opening at ``open_index``.

    Quote- and nesting-aware, so a brace inside a string literal does not close
    the object early. Returns ``None`` if never balanced.
    """
    if open_index >= len(text) or text[open_index] != "{":
        return None
    depth = 0
    in_string = False
    quote = ""
    escaped = False
    for j in range(open_index, len(text)):
        ch = text[j]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_index : j + 1]
    return None


def _iter_json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object embedded in ``text`` (fenced or bare), in order.

    Scans for ``{``, extracts the balanced group, and keeps it if it parses as a
    JSON object — so a ```` ```json {...} ```` fence or an inline object is found
    without the fence markers mattering. Nested objects are skipped (the scan
    resumes past a matched object), so an object's own fields are not re-yielded.
    """
    objects: list[dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            group = _extract_brace_group(text, i)
            if group is not None:
                try:
                    parsed = json.loads(group)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    objects.append(parsed)
                    i += len(group)
                    continue
        i += 1
    return objects


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
    "parse_text_actions",
]
