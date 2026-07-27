# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the single-run harness (harness.runner): run_one / replay / verify."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fakes.backend import FakeBackend, ScriptedTurn

from agent.tools import ToolLayer
from harness import corpus, persistence
from harness.matrix import completed_counts, spend_by_backend
from harness.record import FailureMode, Outcome
from harness.runner import RunSettings, replay_run, run_one, verify_binary
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import EnumerateResult
from validator.runner_test_helpers import succeeding_client

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canned_enumerator(**_: object) -> EnumerateResult:
    return EnumerateResult(
        binary_path="sample-overflow",
        total_found=2,
        returned=2,
        truncated=False,
        gadgets=[Gadget("0x4011ad", "pop rdi ; ret", 2), Gadget("0x4011ae", "ret", 1)],
    )


def _tools() -> ToolLayer:
    return ToolLayer(enumerate_fn=_canned_enumerator)


def _submit_turn(payload_hex: str, addresses: list[str]) -> ScriptedTurn:
    return ScriptedTurn(
        text="submitting",
        tool_calls=[
            {
                "id": "s1",
                "name": "submit_payload",
                "input": {"payload_hex": payload_hex, "chain_addresses": addresses},
            }
        ],
        prompt_tokens=100,
        completion_tokens=20,
        cost_usd=0.0007,
    )


def _giveup_backend() -> FakeBackend:
    # A model that reasons without acting: the huge token count ends the run on
    # the real token budget after one call (ADR 0015 — no give-up path).
    return FakeBackend(
        script=[ScriptedTurn(text="no viable chain; giving up", completion_tokens=10_000_000)]
    )


# --------------------------------------------------------------------------- #
# RunSettings                                                                  #
# --------------------------------------------------------------------------- #


def test_run_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUN_OUTPUT_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("RUN_TOKEN_CAP", "1234")
    monkeypatch.setenv("RUN_WALL_CLOCK_CAP_SECONDS", "2.5")
    settings = RunSettings.from_env()
    assert settings.output_dir == tmp_path / "runs"
    assert settings.token_cap == 1234
    assert settings.wall_clock_cap_seconds == 2.5


def test_run_settings_overrides_win(tmp_path: Path) -> None:
    settings = RunSettings.from_env(output_dir=tmp_path, token_cap=42)
    assert settings.output_dir == tmp_path
    assert settings.token_cap == 42


# --------------------------------------------------------------------------- #
# run_one — writes a valid run directory (done-when #1)                        #
# --------------------------------------------------------------------------- #


def test_run_one_writes_valid_run_directory(fixture_corpus: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", max_nudges=0)

    record = run_one(spec, _giveup_backend(), "zero_shot", settings, tools=_tools())

    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    assert run_dir.is_dir()
    # No leftover partial directory (atomic).
    assert list(settings.output_dir.glob(".partial-*")) == []

    # record.json deserializes through the schema.
    reloaded = persistence.load_record(run_dir)
    assert reloaded.run_id == record.run_id
    assert reloaded.outcome == Outcome.FAILURE

    # trace.jsonl: one JSON object per node transition. A model that never acts
    # reasons once, then the next reason entry trips the token budget and routes
    # to finalize (ADR 0015): ingest, enumerate, reason, reason, finalize.
    trace_lines = (run_dir / persistence.TRACE_NAME).read_text(encoding="utf-8").splitlines()
    nodes = [json.loads(line)["node"] for line in trace_lines]
    assert nodes == ["ingest", "enumerate", "reason", "reason", "finalize"]


def test_run_one_giveup_has_no_payload(fixture_corpus: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", max_nudges=0)
    record = run_one(spec, _giveup_backend(), "zero_shot", settings, tools=_tools())
    assert record.payload_path is None


def test_run_one_writes_full_conversation(fixture_corpus: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", max_nudges=0)
    record = run_one(spec, _giveup_backend(), "zero_shot", settings, tools=_tools())

    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    conversation = run_dir / persistence.CONVERSATION_NAME
    assert conversation.is_file()
    assert record.conversation_path == conversation

    messages = [json.loads(line) for line in conversation.read_text().splitlines()]
    roles = [m["role"] for m in messages]
    # Captures the seeded system prompt, the assistant turn, and the ingest
    # task/target context presented as a user turn. (Trial 2 removed the free
    # baseline gadget dump — the agent enumerates itself — so it no longer appears.)
    assert "system" in roles
    assert "assistant" in roles
    assert any(m["role"] == "user" and m["content"].startswith("Target binary:") for m in messages)


def test_preflight_smoke_run_reaches_a_non_ropgadget_tool(
    fixture_corpus: Any, tmp_path: Path
) -> None:
    """§7 pre-flight gate: a real run must be able to REACH the newly wired tools
    end-to-end, not merely have them registered — the direct guard against Trial
    1's two-tool gap (TRIAL_2_PLAN.md §1). A run whose model calls a non-ROPgadget
    tool must record it in the schema-v5 telemetry: ``tools_offered`` proves the
    full toolkit was advertised, and ``tool_call_counts`` proves the agent seam
    actually dispatched the call (not a KeyError, not silently dropped). Runs with
    the REAL default ToolLayer (all five extra servers), no baseline hand-out."""
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")
    backend = FakeBackend(
        script=[
            ScriptedTurn(
                text="Analyze the target first.",
                tool_calls=[
                    {
                        "id": "r1",
                        "name": "radare2_analyze_binary",
                        "input": {"binary_path": str(spec.binary_path)},
                    }
                ],
            ),
            # End the run on the real token budget (ADR 0015), no submission.
            ScriptedTurn(text="stopping", completion_tokens=10_000_000),
        ]
    )
    # Real ToolLayer() = the full wired toolkit; no injected enumerator, no docker
    # (the run never submits, so validate never executes a payload).
    record = run_one(spec, backend, "zero_shot", settings, tools=ToolLayer())

    # The full toolkit was advertised to the model (closes the §1 blind spot)...
    assert "radare2_analyze_binary" in record.tools_offered
    assert len(record.tools_offered) >= 6  # core three + the five extra servers' tools
    # ...and the non-ROPgadget call was actually dispatched through the seam.
    assert "radare2_analyze_binary" in record.tool_call_counts


def test_resume_and_cost_cap_key_on_backend_handle(fixture_corpus: Any, tmp_path: Path) -> None:
    # Regression: a record stores backend.name = the MODEL string, but batch resume
    # and the per-backend cost cap must key on the cell's registry HANDLE
    # (backend_handle) — else an interrupted premium/local batch re-runs completed
    # cells and under-counts spend on resume.
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", max_nudges=0)
    # backend.name is the model; the cell handle differs (as for every real
    # premium/local backend).
    backend = FakeBackend(
        script=[ScriptedTurn(text="giving up", cost_usd=0.5, completion_tokens=10_000_000)],
        name="claude-sonnet-4-6",
    )
    record = run_one(
        spec, backend, "zero_shot", settings, tools=_tools(), backend_handle="claude-sonnet"
    )
    assert record.backend_handle == "claude-sonnet"
    assert record.backend.name == "claude-sonnet-4-6"

    counts = completed_counts(settings.output_dir)
    spend = spend_by_backend(settings.output_dir)
    # Keyed by the handle, not the model string.
    assert counts.get(("sample-overflow", "claude-sonnet", "zero_shot")) == 1
    assert ("sample-overflow", "claude-sonnet-4-6", "zero_shot") not in counts
    assert spend.get("claude-sonnet") == 0.5
    assert "claude-sonnet-4-6" not in spend


# --------------------------------------------------------------------------- #
# run_one — successful submission writes payload + SUCCESS (ADR 0009)          #
# --------------------------------------------------------------------------- #


def test_run_one_success(fixture_corpus: Any, documented_exploit: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    payload = documented_exploit.build_payload()
    addresses = [f"0x{a:x}" for a in fixture_corpus.addresses]
    backend = FakeBackend(script=[_submit_turn(payload.hex(), addresses)])
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")

    record = run_one(
        spec,
        backend,
        "zero_shot",
        settings,
        tools=_tools(),
        validator_client=succeeding_client(b"Hello World\n"),
    )

    assert record.outcome == Outcome.SUCCESS
    assert record.failure_mode is None
    # payload.bin lands in the final dir and matches the documented bytes.
    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    assert record.payload_path == run_dir / persistence.PAYLOAD_NAME
    assert record.payload_path.read_bytes() == payload
    assert persistence.load_record(run_dir).outcome == Outcome.SUCCESS


# --------------------------------------------------------------------------- #
# run_one — budget caps (done-when #2)                                         #
# --------------------------------------------------------------------------- #


def test_run_one_token_cap_yields_token_budget(fixture_corpus: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    looping = [
        ScriptedTurn(
            tool_calls=[{"id": "e", "name": "enumerate_gadgets", "input": {}}],
            prompt_tokens=500,
            completion_tokens=500,
        )
        for _ in range(20)
    ]
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", token_cap=1500)
    record = run_one(spec, FakeBackend(script=looping), "zero_shot", settings, tools=_tools())
    assert record.outcome == Outcome.FAILURE
    assert record.failure_mode == FailureMode.TOKEN_BUDGET  # schema v5 granular mode


def test_run_one_wall_clock_cap_yields_wall_clock(fixture_corpus: Any, tmp_path: Path) -> None:
    class _SleepyBackend(FakeBackend):
        def chat(self, *args: Any, **kwargs: Any) -> Any:
            time.sleep(0.05)
            return super().chat(*args, **kwargs)

    spec = corpus.resolve_binary("sample-overflow")
    looping = [
        ScriptedTurn(tool_calls=[{"id": "e", "name": "enumerate_gadgets", "input": {}}])
        for _ in range(20)
    ]
    settings = RunSettings.from_env(output_dir=tmp_path / "runs", wall_clock_cap_seconds=0.01)
    record = run_one(spec, _SleepyBackend(script=looping), "zero_shot", settings, tools=_tools())
    assert record.outcome == Outcome.FAILURE
    assert record.failure_mode == FailureMode.WALL_CLOCK  # schema v5 granular mode


# --------------------------------------------------------------------------- #
# replay (done-when #4)                                                        #
# --------------------------------------------------------------------------- #


def test_replay_reruns_validator_without_mutating_record(
    fixture_corpus: Any, documented_exploit: Any, tmp_path: Path
) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    payload = documented_exploit.build_payload()
    addresses = [f"0x{a:x}" for a in fixture_corpus.addresses]
    backend = FakeBackend(script=[_submit_turn(payload.hex(), addresses)])
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")
    record = run_one(
        spec,
        backend,
        "zero_shot",
        settings,
        tools=_tools(),
        validator_client=succeeding_client(b"Hello World\n"),
    )
    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    before = (run_dir / persistence.RECORD_NAME).read_bytes()

    original, output = replay_run(
        str(record.run_id),
        output_dir=settings.output_dir,
        validator_client=succeeding_client(b"Hello World\n"),
    )

    assert output.succeeded
    assert output.stdout_marker_found
    assert original.run_id == record.run_id
    # The stored record.json is untouched by replay.
    assert (run_dir / persistence.RECORD_NAME).read_bytes() == before


# --------------------------------------------------------------------------- #
# verify (corpus-truth)                                                        #
# --------------------------------------------------------------------------- #


def test_verify_binary_reproduces_documented_exploit(fixture_corpus: Any) -> None:
    output = verify_binary("sample-overflow", validator_client=succeeding_client(b"Hello World\n"))
    assert output.succeeded
    assert output.stdout_marker_found
    # verify feeds the documented chain, so its fingerprint is recorded.
    assert output.chain_fingerprint is not None


def test_verify_binary_missing_exploit_raises(fixture_corpus: Any) -> None:
    # Remove the exploit module so the documented-exploit loader fails cleanly.
    (fixture_corpus.root / "exploits" / "sample-overflow.py").unlink()
    with pytest.raises(corpus.CorpusError):
        verify_binary("sample-overflow", validator_client=succeeding_client(b"x"))
