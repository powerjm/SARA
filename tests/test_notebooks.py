# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the analysis notebooks (Step 6).

Structural checks on every committed notebook plus a single real headless
execution (the same path ``make notebooks`` uses) to guard against drift between
the notebooks and the analysis API.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

NOTEBOOK_DIR = Path("analysis/notebooks")

# The committed report set. This is a DELIBERATE MANIFEST, not a frozen snapshot:
# unlike the old two-tool ``test_specs_advertise_...`` lock (which asserted a set
# *narrower than the experiment required* and so silently suppressed the five
# unwired MCP tools — see TRIAL_2_PLAN.md section 1), nothing here is a
# capability the pipeline needs but lacks. Every entry is an intended deliverable;
# the equality assertion is a tripwire so adding or removing a report is a
# conscious edit to this list, reviewed alongside the notebook. When you add a
# report, add its stem here — the structural + no-output checks below then cover
# it automatically via parametrization.
EXPECTED = [
    "01_outcome_omnibus",
    "02_outcome_pairwise",
    "03_time_cost_omnibus",
    "04_time_cost_pairwise",
    "05_success_intervals",
    "06_failure_mode_crosstab",
    "07_strategy_effect",
    "08_progress_tier",
    "09_bonus_score",
]


def _source(stem: str) -> str:
    nb = nbformat.read(NOTEBOOK_DIR / f"{stem}.ipynb", as_version=4)  # type: ignore[no-untyped-call]
    return "\n".join(c.source for c in nb.cells)


def test_committed_notebook_set_is_exactly_expected() -> None:
    present = sorted(p.stem for p in NOTEBOOK_DIR.glob("*.ipynb"))
    assert present == sorted(EXPECTED)


@pytest.mark.parametrize("stem", EXPECTED)
def test_notebook_is_valid_and_orchestrates(stem: str) -> None:
    nb = nbformat.read(NOTEBOOK_DIR / f"{stem}.ipynb", as_version=4)  # type: ignore[no-untyped-call]
    nbformat.validate(nb)
    src = _source(stem)
    # Each notebook loads via load_all, aggregates, calls a stats test, saves a
    # figure, and ends with a copy-pasteable Markdown summary.
    assert "load_runs.load_all()" in src
    assert "aggregate_runs" in src
    assert "st." in src  # calls at least one analysis.stats test
    assert "load_runs.save_figure" in src
    assert "Markdown(" in src


@pytest.mark.parametrize("stem", EXPECTED)
def test_committed_notebooks_have_no_embedded_outputs(stem: str) -> None:
    nb = nbformat.read(NOTEBOOK_DIR / f"{stem}.ipynb", as_version=4)  # type: ignore[no-untyped-call]
    for cell in nb.cells:
        if cell.cell_type == "code":
            assert cell.outputs == []
            assert cell.execution_count is None


def test_one_notebook_executes_headless(tmp_path: Path) -> None:
    """Execute a representative notebook the way ``make notebooks`` does."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--ExecutePreprocessor.timeout=300",
            "--output-dir",
            str(tmp_path),
            str(NOTEBOOK_DIR / "01_outcome_omnibus.ipynb"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "01_outcome_omnibus.ipynb").is_file()
