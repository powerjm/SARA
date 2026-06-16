"""Tests for analysis.aggregate.

Validates the anyOf-success and median-collapse rules at the cell level,
and the shape of the outcome / metric matrices fed to scipy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from analysis.aggregate import (
    aggregate_runs,
    build_metric_matrix,
    build_outcome_matrix,
)
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


def _record(
    binary: str,
    backend_name: str,
    outcome: Outcome,
    *,
    wall: float = 100.0,
    cost: float = 0.10,
    iters: int = 5,
    failure_mode: FailureMode | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=uuid4(),
        binary_id=binary,
        backend=BackendInfo(
            category=BackendCategory.PREMIUM,
            name=backend_name,
            version=backend_name,
        ),
        prompting_strategy=PromptingStrategy.ZERO_SHOT,
        started_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        wall_clock_seconds=wall,
        iterations=iters,
        tokens=TokenUsage(prompt=100, completion=50),
        cost=CostRecord(usd=cost),
        trace_path=Path("runs/x/trace.jsonl"),
        outcome=outcome,
        failure_mode=failure_mode,
    )


def test_anyof_success_collapses_to_success_cell() -> None:
    runs = [
        _record("b1", "claude", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b1", "claude", Outcome.KNOWN_REDISCOVERY),
        _record("b1", "claude", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    assert len(summaries) == 1
    assert summaries[0].success == 1
    assert summaries[0].n_runs == 3


def test_all_failure_collapses_to_failure_cell() -> None:
    runs = [
        _record("b1", "claude", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b1", "claude", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    assert summaries[0].success == 0


def test_all_refused_flag() -> None:
    runs = [
        _record("b1", "claude", Outcome.SAFEGUARD_REFUSAL),
        _record("b1", "claude", Outcome.SAFEGUARD_REFUSAL),
    ]
    summaries = aggregate_runs(runs)
    assert summaries[0].refused_all is True
    assert summaries[0].success == 0


def test_median_collapse_for_wallclock() -> None:
    runs = [
        _record("b1", "claude", Outcome.FAILURE, wall=10, failure_mode=FailureMode.OTHER),
        _record("b1", "claude", Outcome.FAILURE, wall=20, failure_mode=FailureMode.OTHER),
        _record("b1", "claude", Outcome.FAILURE, wall=100, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    assert summaries[0].median_wall_clock_s == 20  # median, not mean


def test_outcome_matrix_shape() -> None:
    runs = [
        _record("b1", "A", Outcome.KNOWN_REDISCOVERY),
        _record("b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b2", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b2", "B", Outcome.NEW_DISCOVERY),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_outcome_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b1", "b2"]
    assert matrix == [[1, 0], [0, 1]]


def test_metric_matrix_shape() -> None:
    runs = [
        _record("b1", "A", Outcome.FAILURE, wall=10, failure_mode=FailureMode.OTHER),
        _record("b1", "B", Outcome.FAILURE, wall=20, failure_mode=FailureMode.OTHER),
        _record("b2", "A", Outcome.FAILURE, wall=30, failure_mode=FailureMode.OTHER),
        _record("b2", "B", Outcome.FAILURE, wall=40, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_metric_matrix(summaries, metric="wall_clock", backends=["A", "B"])
    assert binary_ids == ["b1", "b2"]
    assert matrix == [[10.0, 20.0], [30.0, 40.0]]


def test_metric_matrix_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        build_metric_matrix([], metric="vibes", backends=["A"])
