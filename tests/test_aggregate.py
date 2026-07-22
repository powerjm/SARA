# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

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
    collect_success_chains,
)
from analysis.stats import chain_uniqueness
from harness.record import (
    BackendCategory,
    BackendInfo,
    CostRecord,
    FailureMode,
    Outcome,
    PromptingStrategy,
    RunRecord,
    TokenUsage,
    ValidatorOutput,
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
        _record("b1", "claude", Outcome.SUCCESS),
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
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b2", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b2", "B", Outcome.SUCCESS),
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


# --------------------------------------------------------------------------- #
# Chain uniqueness (ADR 0009)                                                  #
# --------------------------------------------------------------------------- #


def _success_with_chain(binary: str, backend_name: str, fingerprint: str | None) -> RunRecord:
    validator = ValidatorOutput(
        succeeded=True,
        return_code=0,
        stdout_marker_found=True,
        marker_in_payload=False,
        chain_fingerprint=fingerprint,
    )
    r = _record(binary, backend_name, Outcome.SUCCESS)
    return r.model_copy(update={"validator": validator})


def test_collect_success_chains_only_gathers_fingerprinted_successes() -> None:
    runs = [
        _success_with_chain("b1", "A", "aa"),
        _success_with_chain("b1", "B", "bb"),
        _success_with_chain("b1", "C", None),  # success without a committed chain
        _record("b1", "D", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _success_with_chain("b2", "A", "cc"),
    ]
    chains = collect_success_chains(runs)
    assert chains["b1"] == [("A", "aa"), ("B", "bb")]  # C (no fingerprint) and D dropped
    assert chains["b2"] == [("A", "cc")]


def test_chain_uniqueness_counts_distinct_and_unique_chains() -> None:
    # A and B rediscovered the same chain; C found its own.
    chains = [("A", "shared"), ("B", "shared"), ("C", "solo")]
    result = chain_uniqueness("b1", chains)
    assert result.n_success_runs == 3
    assert result.n_distinct_chains == 2
    assert result.n_unique_chains == 1  # only "solo" was found by exactly one backend
    assert result.unique_discoverers == ("C",)
    assert result.distinct_ratio == pytest.approx(2 / 3)


def test_chain_uniqueness_empty_is_all_zero() -> None:
    result = chain_uniqueness("b1", [])
    assert result.n_success_runs == 0
    assert result.n_distinct_chains == 0
    assert result.unique_discoverers == ()
    assert result.distinct_ratio == 0.0
