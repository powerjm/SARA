"""Tests for the backend registry.

These tests exercise the registry's bookkeeping without instantiating any
real backend (which would require API credentials).
"""

from __future__ import annotations

import pytest

from backends import registry
from backends.base import Backend, ChatResponse, Message, ToolSpec
from harness.record import BackendCategory, CostRecord, TokenUsage


class _FakeBackend(Backend):
    """Test double: never makes a network call."""

    def __init__(self) -> None:
        super().__init__(temperature=0.0, seed=0)
        self.name = "fake-backend"
        self.version = "fake-1"
        self.category = BackendCategory.PREMIUM

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> ChatResponse:
        return ChatResponse(
            text="fake",
            tool_calls=[],
            tokens=TokenUsage(prompt=1, completion=1),
            cost=CostRecord(usd=0.0),
            raw=None,
        )

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_register_and_resolve_round_trip() -> None:
    name = "fake-test-only-do-not-collide"
    registry.register(name, BackendCategory.PREMIUM, _FakeBackend)
    try:
        b = registry.get(name)
        assert b.name == "fake-backend"
        assert name in registry.known()
    finally:
        # Clean up so other tests don't see this entry.
        registry._REGISTRY.pop(name, None)


def test_register_rejects_duplicate() -> None:
    name = "fake-dup"
    registry.register(name, BackendCategory.PREMIUM, _FakeBackend)
    try:
        with pytest.raises(ValueError, match="already registered"):
            registry.register(name, BackendCategory.PREMIUM, _FakeBackend)
    finally:
        registry._REGISTRY.pop(name, None)


def test_get_unknown_backend_raises() -> None:
    with pytest.raises(KeyError, match="unknown backend"):
        registry.get("definitely-not-registered")


def test_defaults_present() -> None:
    # Claude entries should be wired by _register_defaults at import time.
    assert "claude-sonnet" in registry.known()
    assert "claude-opus" in registry.known()


def test_temperature_out_of_range_rejected() -> None:
    class _Bad(_FakeBackend):
        def __init__(self) -> None:
            Backend.__init__(self, temperature=99.0)

    with pytest.raises(ValueError, match="temperature out of range"):
        _Bad()


# --- Refusal detection (backends.base.Backend.detect_refusal) ------------- #


def _response(text: str, raw: object = None) -> ChatResponse:
    return ChatResponse(
        text=text,
        tool_calls=[],
        tokens=TokenUsage(prompt=1, completion=1),
        cost=CostRecord(usd=0.0),
        raw=raw,
    )


def test_detect_refusal_keyword_fallback() -> None:
    backend = _FakeBackend()
    assert backend.detect_refusal(_response("I'm sorry, but I must decline."))
    assert not backend.detect_refusal(_response("Here is a pop rdi ; ret gadget."))


def test_detect_refusal_prefers_provider_metadata() -> None:
    backend = _FakeBackend()
    # Stop reason wins even when the text alone looks innocuous.
    assert backend.detect_refusal(_response("(no content)", raw={"stop_reason": "refusal"}))
    assert backend.detect_refusal(_response("", raw={"finish_reason": "content_filter"}))


def test_detect_refusal_metadata_non_refusal_defers_to_keywords() -> None:
    backend = _FakeBackend()
    # A benign stop reason does not veto a keyword hit in the text.
    assert backend.detect_refusal(
        _response("I cannot help with that.", raw={"stop_reason": "end_turn"})
    )
    assert not backend.detect_refusal(
        _response("Working on the chain now.", raw={"stop_reason": "end_turn"})
    )
