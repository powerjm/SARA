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
    return FakeBackend(script=[ScriptedTurn(text="no viable chain; giving up")])


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
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")

    record = run_one(spec, _giveup_backend(), "zero_shot", settings, tools=_tools())

    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    assert run_dir.is_dir()
    # No leftover partial directory (atomic).
    assert list(settings.output_dir.glob(".partial-*")) == []

    # record.json deserializes through the schema.
    reloaded = persistence.load_record(run_dir)
    assert reloaded.run_id == record.run_id
    assert reloaded.outcome == Outcome.FAILURE

    # trace.jsonl: one JSON object per node transition (5 nodes).
    trace_lines = (run_dir / persistence.TRACE_NAME).read_text(encoding="utf-8").splitlines()
    nodes = [json.loads(line)["node"] for line in trace_lines]
    assert nodes == ["ingest", "enumerate", "reason", "propose", "validate"]


def test_run_one_giveup_has_no_payload(fixture_corpus: Any, tmp_path: Path) -> None:
    spec = corpus.resolve_binary("sample-overflow")
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")
    record = run_one(spec, _giveup_backend(), "zero_shot", settings, tools=_tools())
    assert record.payload_path is None


# --------------------------------------------------------------------------- #
# run_one — successful submission writes payload + KNOWN_REDISCOVERY           #
# --------------------------------------------------------------------------- #


def test_run_one_known_rediscovery(
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

    assert record.outcome == Outcome.KNOWN_REDISCOVERY
    assert record.failure_mode is None
    # payload.bin lands in the final dir and matches the documented bytes.
    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    assert record.payload_path == run_dir / persistence.PAYLOAD_NAME
    assert record.payload_path.read_bytes() == payload
    assert persistence.load_record(run_dir).outcome == Outcome.KNOWN_REDISCOVERY


# --------------------------------------------------------------------------- #
# run_one — budget caps (done-when #2)                                         #
# --------------------------------------------------------------------------- #


def test_run_one_token_cap_yields_budget_exhausted(fixture_corpus: Any, tmp_path: Path) -> None:
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
    assert record.failure_mode == FailureMode.BUDGET_EXHAUSTED


def test_run_one_wall_clock_cap_yields_budget_exhausted(
    fixture_corpus: Any, tmp_path: Path
) -> None:
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
    assert record.failure_mode == FailureMode.BUDGET_EXHAUSTED


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
    assert output.matched_documented_chain


def test_verify_binary_missing_exploit_raises(fixture_corpus: Any) -> None:
    # Remove the exploit module so the documented-exploit loader fails cleanly.
    (fixture_corpus.root / "exploits" / "sample-overflow.py").unlink()
    with pytest.raises(corpus.CorpusError):
        verify_binary("sample-overflow", validator_client=succeeding_client(b"x"))
