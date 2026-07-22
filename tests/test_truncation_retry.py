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
Tests for output-truncation detection and the bounded retry (ADR 0013).

A reasoning turn cut off at the per-call output cap loses its tool call (the
``input`` comes back empty/half-written). Before ADR 0013 that was silently
misread as ``tool_use_malformed``; now the harness detects the cut-off, discards
the unusable call, and re-prompts for a concise complete reply, up to a bounded
number of times. These tests cover the detector across provider ``raw`` shapes,
the happy-path recovery, retry exhaustion, and the ``max_truncation_retries``
knob — all on the scripted FakeBackend, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fakes.backend import FakeBackend, ScriptedTurn

from agent import prompts
from agent.graph import AgentConfig, run_agent
from agent.state import BinaryContext
from agent.tools import ToolLayer
from backends.base import ChatResponse
from harness.record import CostRecord, FailureMode, Outcome, TokenUsage
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import EnumerateResult
from validator.runner_test_helpers import succeeding_client

# --------------------------------------------------------------------------- #
# Helpers (mirrors test_agent_graph_integration.py)                           #
# --------------------------------------------------------------------------- #


def _fake_enumerator(**_: object) -> EnumerateResult:
    return EnumerateResult(
        binary_path="sample_overflow",
        total_found=3,
        returned=3,
        truncated=False,
        gadgets=[
            Gadget("0x4011ad", "pop rdi ; ret", 2),
            Gadget("0x4011ae", "ret", 1),
            Gadget("0x401166", "win", 1),
        ],
    )


def _binary(sample_overflow_path: Path) -> BinaryContext:
    return BinaryContext(
        binary_id="sample-overflow",
        binary_path=sample_overflow_path,
        architecture="x86_64",
        protections=["nx"],
    )


def _config(tmp_path: Path, **overrides: Any) -> AgentConfig:
    base: dict[str, Any] = {
        "strategy": prompts.get("zero_shot"),
        "tools": ToolLayer(enumerate_fn=_fake_enumerator),
        "success_marker": "Hello World",
        "validator_client": succeeding_client(b"Hello World\n"),
        "runs_dir": tmp_path / "runs",
    }
    base.update(overrides)
    return AgentConfig(**base)


def _submit_turn(payload_hex: str, addresses: list[str]) -> ScriptedTurn:
    return ScriptedTurn(
        text="I have a complete chain; submitting.",
        tool_calls=[
            {
                "id": "submit_1",
                "name": "submit_payload",
                "input": {"payload_hex": payload_hex, "chain_addresses": addresses},
            }
        ],
        prompt_tokens=200,
        completion_tokens=40,
    )


def _truncated_turn() -> ScriptedTurn:
    """A reply cut off at the cap: a submit_payload whose input never arrived."""
    return ScriptedTurn(
        text="Assembling the chain: pop rdi; ret ... (cut off before finishing",
        tool_calls=[{"id": "s0", "name": "submit_payload", "input": {}}],
        prompt_tokens=500,
        completion_tokens=16_384,
        stop_reason="max_tokens",
    )


def _resp(raw: Any) -> ChatResponse:
    return ChatResponse(
        text="",
        tool_calls=[],
        tokens=TokenUsage(prompt=0, completion=0),
        cost=CostRecord(usd=0.0),
        raw=raw,
    )


# --------------------------------------------------------------------------- #
# detect_truncation — provider raw shapes                                     #
# --------------------------------------------------------------------------- #


def test_detect_truncation_matches_each_provider_stop_reason() -> None:
    backend = FakeBackend(script=[])
    # Anthropic stop_reason, OpenAI-family finish_reason, Gemini enum str().
    assert backend.detect_truncation(_resp({"stop_reason": "max_tokens"})) is True
    assert backend.detect_truncation(_resp({"finish_reason": "length"})) is True
    assert backend.detect_truncation(_resp({"finish_reason": "MAX_TOKENS"})) is True
    assert backend.detect_truncation(_resp({"finish_reason": "FinishReason.MAX_TOKENS"})) is True


def test_detect_truncation_false_for_normal_and_other_stops() -> None:
    backend = FakeBackend(script=[])
    for raw in (
        {"stop_reason": "end_turn"},
        {"stop_reason": "tool_use"},
        {"stop_reason": "refusal"},
        {"finish_reason": "stop"},
        {"finish_reason": "tool_calls"},
        {"finish_reason": "SAFETY"},
        {},  # no stop reason at all
        "not-a-dict",  # raw is not a mapping
        None,
    ):
        assert backend.detect_truncation(_resp(raw)) is False


# --------------------------------------------------------------------------- #
# Recovery, exhaustion, and the knob                                          #
# --------------------------------------------------------------------------- #


def test_truncated_turn_recovers_on_retry(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    """A cut-off turn is discarded and re-prompted; the retry submits and wins."""
    payload = documented_exploit.build_payload()
    addresses = [int(a, 16) for a in documented_exploit.load_chain()["documented_gadget_addresses"]]
    backend = FakeBackend(
        script=[_truncated_turn(), _submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses])]
    )

    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))

    assert backend.calls_made == 2  # truncated turn + successful retry
    assert result.state.truncation_retries == 1
    assert result.outcome == Outcome.SUCCESS
    assert result.failure_mode is None
    # The concise-reply re-prompt was injected as a user turn before the retry.
    assert any(m.role == "user" and "length limit" in m.content for m in result.state.messages)
    # The truncated (empty) submit_payload was discarded, not proposed.
    assert result.state.candidate_payload_path is not None
    assert result.state.candidate_payload_path.read_bytes() == payload


def test_all_attempts_truncated_yields_truncated_failure(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    """Every attempt cut off -> terminate 'truncated' -> FAILURE / OTHER."""
    backend = FakeBackend(script=[_truncated_turn() for _ in range(5)])

    # Default max_truncation_retries=2 -> 1 + 2 = 3 attempts, then give up.
    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))

    assert backend.calls_made == 3
    assert result.state.truncation_retries == 3
    assert result.state.termination_reason == "truncated"
    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.OTHER
    # A truncation failure is NOT mislabeled as a malformed tool use.
    assert result.failure_mode != FailureMode.TOOL_USE_MALFORMED


def test_truncation_retries_zero_detects_but_does_not_reprompt(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    """With the retry budget at 0, one cut-off attempt still ends as 'truncated'."""
    backend = FakeBackend(script=[_truncated_turn(), _truncated_turn()])

    result = run_agent(
        backend, _binary(sample_overflow_path), _config(tmp_path, max_truncation_retries=0)
    )

    assert backend.calls_made == 1  # no re-prompt
    assert result.state.termination_reason == "truncated"
    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.OTHER
    # No retry nudge was appended.
    assert not any(m.role == "user" and "length limit" in m.content for m in result.state.messages)


def test_truncated_attempts_are_still_billed(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    """Tokens/cost from a truncated attempt are accumulated, not dropped."""
    payload = documented_exploit.build_payload()
    addresses = [int(a, 16) for a in documented_exploit.load_chain()["documented_gadget_addresses"]]
    backend = FakeBackend(
        script=[_truncated_turn(), _submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses])]
    )

    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))

    # 16_384 completion + 500 prompt (truncated) + 40 + 200 (retry) all counted.
    assert result.state.completion_tokens == 16_384 + 40
    assert result.state.prompt_tokens == 500 + 200
