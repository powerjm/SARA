"""Tests for atomic run persistence (harness.persistence)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import persistence
from harness.record import (
    BackendCategory,
    BackendInfo,
    CostRecord,
    FailureMode,
    Outcome,
    PromptingStrategy,
    RunRecord,
    TokenUsage,
)


def _record(binary_id: str = "sample-overflow", outcome: Outcome = Outcome.FAILURE) -> RunRecord:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return RunRecord(
        binary_id=binary_id,
        backend=BackendInfo(category=BackendCategory.PREMIUM, name="fake", version="fake-1"),
        prompting_strategy=PromptingStrategy.ZERO_SHOT,
        started_at=now,
        ended_at=now,
        wall_clock_seconds=0.1,
        outcome=outcome,
        failure_mode=FailureMode.OTHER if outcome == Outcome.FAILURE else None,
        iterations=1,
        tokens=TokenUsage(prompt=10, completion=5),
        cost=CostRecord(usd=0.01),
        trace_path=Path("trace.jsonl"),
    )


def test_begin_run_creates_partial_not_final(tmp_path: Path) -> None:
    partial = persistence.begin_run(tmp_path, "run-1")
    assert partial.is_dir()
    assert partial.name == ".partial-run-1"
    assert not persistence.final_dir(tmp_path, "run-1").exists()


def test_begin_run_clears_stale_partial(tmp_path: Path) -> None:
    partial = persistence.begin_run(tmp_path, "run-1")
    (partial / "leftover.txt").write_text("stale", encoding="utf-8")
    partial2 = persistence.begin_run(tmp_path, "run-1")
    assert partial2 == partial
    assert not (partial2 / "leftover.txt").exists()


def test_begin_run_refuses_existing_final(tmp_path: Path) -> None:
    persistence.final_dir(tmp_path, "run-1").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        persistence.begin_run(tmp_path, "run-1")


def test_write_and_finalize_is_atomic(tmp_path: Path) -> None:
    partial = persistence.begin_run(tmp_path, "run-1")
    (partial / persistence.TRACE_NAME).write_text('{"node":"ingest"}\n', encoding="utf-8")
    persistence.write_record(partial, _record())
    final = persistence.finalize_run(tmp_path, "run-1")

    assert final == persistence.final_dir(tmp_path, "run-1")
    assert (final / persistence.RECORD_NAME).is_file()
    assert (final / persistence.TRACE_NAME).is_file()
    assert not partial.exists()  # partial renamed away


def test_load_record_round_trips(tmp_path: Path) -> None:
    partial = persistence.begin_run(tmp_path, "run-1")
    persistence.write_record(partial, _record(outcome=Outcome.KNOWN_REDISCOVERY))
    final = persistence.finalize_run(tmp_path, "run-1")

    loaded_from_dir = persistence.load_record(final)
    loaded_from_file = persistence.load_record(final / persistence.RECORD_NAME)
    assert loaded_from_dir.outcome == Outcome.KNOWN_REDISCOVERY
    assert loaded_from_file.outcome == Outcome.KNOWN_REDISCOVERY


def test_iter_records_skips_partials(tmp_path: Path) -> None:
    for i in range(3):
        partial = persistence.begin_run(tmp_path, f"run-{i}")
        persistence.write_record(partial, _record())
        persistence.finalize_run(tmp_path, f"run-{i}")
    # A leftover partial dir (crashed run) with a record.json must be ignored.
    stale = persistence.begin_run(tmp_path, "crashed")
    persistence.write_record(stale, _record())

    records = list(persistence.iter_records(tmp_path))
    assert len(records) == 3


def test_iter_records_empty_dir(tmp_path: Path) -> None:
    assert list(persistence.iter_records(tmp_path / "nope")) == []


def test_record_json_is_indented(tmp_path: Path) -> None:
    partial = persistence.begin_run(tmp_path, "run-1")
    path = persistence.write_record(partial, _record())
    # Valid JSON, pretty-printed (multi-line).
    text = path.read_text(encoding="utf-8")
    assert "\n" in text
    json.loads(text)
