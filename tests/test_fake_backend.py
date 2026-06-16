"""Tests for the scripted FakeBackend and its registry wiring."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fakes.backend import FakeBackend, FakeBackendExhausted, ScriptedTurn

from backends import registry
from backends.base import ChatResponse, ToolSpec
from harness.record import BackendCategory

_CASSETTES = Path(__file__).resolve().parent / "fakes" / "cassettes"


def _chat(backend: FakeBackend) -> ChatResponse:
    return backend.chat([], [], max_tokens=64)


def test_script_replays_in_order() -> None:
    backend = FakeBackend(
        script=[
            ScriptedTurn(text="first", completion_tokens=3),
            ScriptedTurn(text="second", completion_tokens=4),
        ]
    )
    assert _chat(backend).text == "first"
    assert _chat(backend).text == "second"
    assert backend.calls_made == 2
    assert backend.turns_remaining == 0


def test_exhausted_script_raises() -> None:
    backend = FakeBackend(script=[ScriptedTurn(text="only")])
    _chat(backend)
    with pytest.raises(FakeBackendExhausted, match="exhausted"):
        _chat(backend)


def test_dict_turns_are_coerced() -> None:
    backend = FakeBackend(script=[{"text": "hi", "prompt_tokens": 7}])
    resp = _chat(backend)
    assert resp.text == "hi"
    assert resp.tokens.prompt == 7


def test_tool_calls_passed_through_and_copied() -> None:
    call = {"id": "c1", "name": "enumerate_gadgets", "input": {"binary_path": "x"}}
    backend = FakeBackend(script=[ScriptedTurn(tool_calls=[call])])
    resp = _chat(backend)
    assert resp.tool_calls == [call]
    # Returned tool-call dicts are copies, not aliases of the script's.
    resp.tool_calls[0]["name"] = "mutated"
    assert call["name"] == "enumerate_gadgets"


def test_stop_reason_surfaces_in_raw_and_drives_refusal() -> None:
    backend = FakeBackend(script=[ScriptedTurn(text="no", stop_reason="refusal")])
    resp = _chat(backend)
    assert resp.raw["stop_reason"] == "refusal"
    assert backend.detect_refusal(resp) is True


def test_non_refusal_stop_reason_defers_to_keywords() -> None:
    backend = FakeBackend(script=[ScriptedTurn(text="all good", stop_reason="end_turn")])
    assert backend.detect_refusal(_chat(backend)) is False


def test_count_tokens_is_positive() -> None:
    assert FakeBackend().count_tokens("") == 1
    assert FakeBackend().count_tokens("abcdefgh") == 2


def test_category_override() -> None:
    backend = FakeBackend(category=BackendCategory.OPEN_WEIGHT)
    assert backend.category == BackendCategory.OPEN_WEIGHT


def test_from_cassette_replays_recorded_turns() -> None:
    backend = FakeBackend.from_cassette(_CASSETTES / "enumerate_then_refuse.jsonl")
    first = _chat(backend)
    assert first.tool_calls[0]["name"] == "enumerate_gadgets"
    assert first.tokens.prompt == 120
    second = _chat(backend)
    assert backend.detect_refusal(second) is True
    with pytest.raises(FakeBackendExhausted):
        _chat(backend)


def test_from_env_without_cassette_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_BACKEND_CASSETTE", raising=False)
    backend = FakeBackend.from_env()
    assert backend.turns_remaining == 0


def test_from_env_reads_cassette_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BACKEND_CASSETTE", str(_CASSETTES / "enumerate_then_refuse.jsonl"))
    backend = FakeBackend.from_env()
    assert backend.turns_remaining == 2


def test_registered_as_fake_under_pytest() -> None:
    # conftest sets PYTEST_RUNNING=1 before the registry is imported.
    assert os.environ.get("PYTEST_RUNNING") == "1"
    assert "fake" in registry.known()
    assert isinstance(registry.get("fake"), FakeBackend)


def test_specs_type_is_tool_spec() -> None:
    # Sanity: ToolSpec import path is stable for backends consuming tool specs.
    assert ToolSpec.__name__ == "ToolSpec"
