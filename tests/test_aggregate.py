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
    build_tier_matrix,
    collect_success_chains,
)
from analysis.stats import chain_uniqueness
from harness.record import (
    BackendCategory,
    BackendInfo,
    CostRecord,
    FailureMode,
    MaxTier,
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
    max_tier: MaxTier | None = None,
) -> RunRecord:
    # By construction MARKER == SUCCESS, so default a SUCCESS run to MARKER and
    # everything else to NONE (tests that exercise RAN/CONTROL pass max_tier).
    if max_tier is None:
        max_tier = MaxTier.MARKER if outcome == Outcome.SUCCESS else MaxTier.NONE
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
        max_tier_reached=max_tier,
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


def test_outcome_matrix_excludes_all_refused_cell_and_drops_binary() -> None:
    # B refused on every run for b1 -> b1 has no scorable B cell -> b1 is dropped
    # rather than counting B as a 0 (a refusal is "wouldn't", not "couldn't").
    runs = [
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.SAFEGUARD_REFUSAL),
        _record("b2", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
        _record("b2", "B", Outcome.SUCCESS),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_outcome_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b2"]
    assert matrix == [[0, 1]]


def test_outcome_matrix_partially_refused_cell_still_scores_as_failure() -> None:
    # b1/B has one refusal AND one genuine mechanical failure -> refused_all is
    # False -> the cell is a real "couldn't", scored 0 and retained.
    runs = [
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.SAFEGUARD_REFUSAL),
        _record("b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_outcome_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b1"]
    assert matrix == [[1, 0]]


def test_outcome_matrix_drops_binary_with_missing_backend() -> None:
    # B was never run on b2 -> b2 dropped so the matrix stays fully paired.
    runs = [
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.SUCCESS),
        _record("b2", "A", Outcome.SUCCESS),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_outcome_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b1"]
    assert matrix == [[1, 1]]


def test_metric_matrix_drops_binary_with_missing_cell() -> None:
    # C never run on b2 -> b2 dropped (previously became a NaN row that poisoned
    # the whole Friedman/Wilcoxon omnibus).
    runs = [
        _record("b1", "A", Outcome.FAILURE, wall=10, failure_mode=FailureMode.OTHER),
        _record("b1", "B", Outcome.FAILURE, wall=20, failure_mode=FailureMode.OTHER),
        _record("b1", "C", Outcome.FAILURE, wall=30, failure_mode=FailureMode.OTHER),
        _record("b2", "A", Outcome.FAILURE, wall=40, failure_mode=FailureMode.OTHER),
        _record("b2", "B", Outcome.FAILURE, wall=50, failure_mode=FailureMode.OTHER),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_metric_matrix(
        summaries, metric="wall_clock", backends=["A", "B", "C"]
    )
    assert binary_ids == ["b1"]
    assert matrix == [[10.0, 20.0, 30.0]]


# --------------------------------------------------------------------------- #
# Progress tier — max collapse + ordinal matrix (D5)                           #
# --------------------------------------------------------------------------- #


def test_max_tier_collapses_best_of_n() -> None:
    # A cell whose runs reached NONE / RAN / CONTROL collapses to CONTROL (the
    # best rung), not the median or the last — best-of-N, mirroring any-success.
    runs = [
        _record("b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.NONE),
        _record("b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.RAN),
        _record(
            "b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.CONTROL
        ),
    ]
    summaries = aggregate_runs(runs)
    assert len(summaries) == 1
    assert summaries[0].max_tier == MaxTier.CONTROL
    assert summaries[0].success == 0  # CONTROL is short of a shell


def test_max_tier_marker_matches_success_invariant() -> None:
    # MARKER is exactly SUCCESS: a cell with one MARKER run is both success==1
    # and max_tier==MARKER — the two collapse rules agree at the top rung.
    runs = [
        _record("b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.RAN),
        _record("b1", "A", Outcome.SUCCESS),  # -> MARKER
    ]
    summaries = aggregate_runs(runs)
    assert summaries[0].success == 1
    assert summaries[0].max_tier == MaxTier.MARKER


def test_tier_counts_histogram_sums_to_n_runs() -> None:
    # tier_counts is the per-rung histogram aligned to MAX_TIER_ORDER
    # (NONE, RAN, CONTROL, MARKER) and must sum to n_runs.
    runs = [
        _record("b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.NONE),
        _record("b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.NONE),
        _record(
            "b1", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.CONTROL
        ),
        _record("b1", "A", Outcome.SUCCESS),  # -> MARKER
    ]
    summaries = aggregate_runs(runs)
    assert summaries[0].tier_counts == (2, 0, 1, 1)  # NONE=2, RAN=0, CONTROL=1, MARKER=1
    assert sum(summaries[0].tier_counts) == summaries[0].n_runs


def test_tier_matrix_shape_uses_ordinal_ranks() -> None:
    # Cells carry the ordinal rank (NONE=0, RAN=1, CONTROL=2, MARKER=3) of the
    # best rung, in the same (n_binaries x k_backends) shape as the outcome matrix.
    runs = [
        _record("b1", "A", Outcome.SUCCESS),  # MARKER -> 3
        _record(
            "b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.CONTROL
        ),  # -> 2
        _record(
            "b2", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.RAN
        ),  # -> 1
        _record(
            "b2", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.NONE
        ),  # -> 0
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_tier_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b1", "b2"]
    assert matrix == [[3, 2], [1, 0]]


def test_tier_matrix_excludes_all_refused_cell_and_drops_binary() -> None:
    # Same missing-data policy as the outcome matrix: an all-refused cell is
    # missing (not a tier-0), so its binary is dropped rather than counting the
    # refusal as "got nowhere".
    runs = [
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.SAFEGUARD_REFUSAL),
        _record("b2", "A", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.RAN),
        _record(
            "b2", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.CONTROL
        ),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_tier_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b2"]
    assert matrix == [[1, 2]]


def test_tier_matrix_partially_refused_cell_uses_best_real_tier() -> None:
    # A cell mixing a refusal with a real CONTROL attempt is not all-refused, so
    # it is retained at the best real rung (CONTROL=2), not dropped.
    runs = [
        _record("b1", "A", Outcome.SUCCESS),  # MARKER -> 3
        _record("b1", "B", Outcome.SAFEGUARD_REFUSAL),  # -> NONE, but...
        _record(
            "b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.CONTROL
        ),  # best real -> 2
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_tier_matrix(summaries, backends=["A", "B"])
    assert binary_ids == ["b1"]
    assert matrix == [[3, 2]]


def test_tier_matrix_strategy_filter() -> None:
    # strategy=None mixes strategies per cell key; the builder honours an explicit
    # strategy filter the same way build_outcome_matrix does.
    runs = [
        _record("b1", "A", Outcome.SUCCESS),
        _record("b1", "B", Outcome.FAILURE, failure_mode=FailureMode.OTHER, max_tier=MaxTier.RAN),
    ]
    summaries = aggregate_runs(runs)
    binary_ids, matrix = build_tier_matrix(
        summaries, backends=["A", "B"], strategy=str(PromptingStrategy.ZERO_SHOT)
    )
    assert binary_ids == ["b1"]
    assert matrix == [[3, 1]]
    # A non-matching strategy filter yields an empty, fully-paired matrix.
    ids_none, mat_none = build_tier_matrix(summaries, backends=["A", "B"], strategy="react")
    assert ids_none == []
    assert mat_none == []


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
