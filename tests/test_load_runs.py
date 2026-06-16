"""Tests for analysis.load_runs (the notebook plumbing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis import load_runs, synthetic
from harness import persistence
from harness.record import Outcome


def test_load_all_falls_back_to_synthetic(tmp_path: Path) -> None:
    records = load_runs.load_all(tmp_path / "empty", seed=0)
    assert records  # non-empty
    # Deterministic: same seed -> same first run id.
    again = load_runs.load_all(tmp_path / "empty", seed=0)
    assert records[0].run_id == again[0].run_id


def test_load_all_reads_real_runs(tmp_path: Path) -> None:
    # Persist two real synthetic records and confirm they are loaded (no fallback).
    recs = synthetic.generate(seed=1, n_binaries=2, replicates=1)[:2]
    for i, rec in enumerate(recs):
        partial = persistence.begin_run(tmp_path, f"r{i}")
        persistence.write_record(partial, rec)
        persistence.finalize_run(tmp_path, f"r{i}")

    loaded = load_runs.load_all(tmp_path, fallback_synthetic=False)
    assert len(loaded) == 2


def test_no_fallback_returns_empty(tmp_path: Path) -> None:
    assert load_runs.load_all(tmp_path / "empty", fallback_synthetic=False) == []


def test_axes_helpers() -> None:
    records = load_runs.load_all(Path("/nonexistent-runs"), seed=0)
    assert len(load_runs.backend_names(records)) == 3
    assert set(load_runs.strategies(records)) == {"zero_shot", "chain_of_thought", "react"}
    cats = load_runs.category_of(records)
    assert set(cats.values()) == {"premium", "open_weight", "unrestricted"}


def test_difficulty_tier_synthetic_convention() -> None:
    assert load_runs.difficulty_tier("syn-bin-00") == 0
    assert load_runs.difficulty_tier("syn-bin-05") == 1  # 5 % 4
    assert load_runs.difficulty_tier("not-a-binary") is None


def test_tiers_present_in_synthetic() -> None:
    records = load_runs.load_all(Path("/nonexistent-runs"), seed=0)
    assert load_runs.tiers(records) == [0, 1, 2, 3]


def test_save_figure_writes_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_runs, "FIGURES_ROOT", tmp_path / "figs")
    plt = load_runs.pin_style(seed=0)
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    path = load_runs.save_figure(fig, "test_stem", "line")
    assert path.is_file()
    assert path.parent.name == "test_stem"


def test_synthetic_dataset_covers_all_outcomes() -> None:
    records = load_runs.load_all(Path("/nonexistent-runs"), seed=0)
    assert {r.outcome for r in records} == set(Outcome)
