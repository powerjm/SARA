"""
FakeBackend: a scripted, network-free :class:`~backends.base.Backend`.

The whole agent loop is testable end-to-end without spending money or holding an
API key by replaying a fixed list of responses. Two ways to build one:

* ``FakeBackend(script=[ScriptedTurn(...), ...])`` — replays the turns in order
  and raises :class:`FakeBackendExhausted` once they run out (an over-long run
  is a test bug, not a silent hang).
* ``FakeBackend.from_cassette(path)`` — replays a recorded JSONL cassette, one
  turn per line. ``from_env()`` reads the path from ``FAKE_BACKEND_CASSETTE``.

A turn may carry a provider ``stop_reason`` (e.g. ``"refusal"``); it surfaces in
``ChatResponse.raw`` so the base-class ``detect_refusal`` picks it up from
metadata, exactly as a real provider would. This lives under ``tests/`` because
it is test scaffolding, but the registry exposes it as the ``"fake"`` backend
when ``PYTEST_RUNNING=1`` so CLI-level tests can resolve it by name.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backends.base import Backend, ChatResponse, Message, ToolSpec
from harness.record import BackendCategory, CostRecord, TokenUsage


class FakeBackendExhausted(RuntimeError):
    """Raised when ``chat`` is called more times than the script has turns."""


@dataclass
class ScriptedTurn:
    """One scripted backend response.

    ``tool_calls`` are passed through verbatim (Anthropic-style ``input`` dicts).
    ``stop_reason`` mimics provider metadata; set it to ``"refusal"`` to exercise
    metadata-based refusal detection.
    """

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stop_reason: str | None = None
    cost_usd: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScriptedTurn:
        """Build a turn from a cassette line; unknown keys are ignored."""
        return cls(
            text=str(data.get("text", "")),
            tool_calls=list(data.get("tool_calls") or []),
            prompt_tokens=int(data.get("prompt_tokens", 0)),
            completion_tokens=int(data.get("completion_tokens", 0)),
            stop_reason=data.get("stop_reason"),
            cost_usd=float(data.get("cost_usd", 0.0)),
        )


# Accept either ready ScriptedTurns or plain dicts in a script.
ScriptEntry = ScriptedTurn | dict[str, Any]


class FakeBackend(Backend):
    """A backend that replays scripted responses. No network, no API key."""

    category = BackendCategory.PREMIUM

    def __init__(
        self,
        script: Sequence[ScriptEntry] | None = None,
        *,
        name: str = "fake",
        version: str = "fake-1",
        category: BackendCategory | None = None,
        temperature: float = 0.0,
        seed: int | None = 0,
    ) -> None:
        super().__init__(temperature=temperature, seed=seed)
        self.name = name
        self.version = version
        if category is not None:
            self.category = category
        self._script: list[ScriptedTurn] = [_coerce_turn(turn) for turn in (script or [])]
        self._cursor = 0

    # --- Interface ------------------------------------------------------- #

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> ChatResponse:
        if self._cursor >= len(self._script):
            raise FakeBackendExhausted(
                f"FakeBackend script exhausted after {self._cursor} call(s); "
                "the run asked for more responses than were scripted."
            )
        turn = self._script[self._cursor]
        index = self._cursor
        self._cursor += 1
        return ChatResponse(
            text=turn.text,
            tool_calls=[dict(call) for call in turn.tool_calls],
            tokens=TokenUsage(prompt=turn.prompt_tokens, completion=turn.completion_tokens),
            cost=CostRecord(usd=turn.cost_usd),
            raw={"stop_reason": turn.stop_reason, "turn_index": index},
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    # --- Introspection (for assertions) --------------------------------- #

    @property
    def calls_made(self) -> int:
        return self._cursor

    @property
    def turns_remaining(self) -> int:
        return len(self._script) - self._cursor

    # --- Constructors --------------------------------------------------- #

    @classmethod
    def from_cassette(cls, path: str | Path, **kwargs: Any) -> FakeBackend:
        """Build from a JSONL cassette (one turn per line; blank lines ignored)."""
        turns: list[ScriptEntry] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            turns.append(ScriptedTurn.from_dict(json.loads(stripped)))
        return cls(script=turns, **kwargs)

    @classmethod
    def from_env(cls) -> FakeBackend:
        """Registry factory: a cassette from ``FAKE_BACKEND_CASSETTE`` or empty."""
        cassette = os.environ.get("FAKE_BACKEND_CASSETTE")
        if cassette:
            return cls.from_cassette(Path(cassette))
        return cls(script=[])


def _coerce_turn(turn: ScriptEntry) -> ScriptedTurn:
    return turn if isinstance(turn, ScriptedTurn) else ScriptedTurn.from_dict(turn)


__all__ = ["FakeBackend", "FakeBackendExhausted", "ScriptedTurn"]
