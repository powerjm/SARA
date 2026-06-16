"""Tests for the analysis notebooks (Step 6).

Structural checks on all seven notebooks plus a single real headless execution
(the same path ``make notebooks`` uses) to guard against drift between the
notebooks and the analysis API.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

NOTEBOOK_DIR = Path("analysis/notebooks")
EXPECTED = [
    "01_outcome_omnibus",
    "02_outcome_pairwise",
    "03_time_cost_omnibus",
    "04_time_cost_pairwise",
    "05_success_intervals",
    "06_failure_mode_crosstab",
    "07_strategy_effect",
]


def _source(stem: str) -> str:
    nb = nbformat.read(NOTEBOOK_DIR / f"{stem}.ipynb", as_version=4)  # type: ignore[no-untyped-call]
    return "\n".join(c.source for c in nb.cells)


def test_all_seven_notebooks_exist() -> None:
    present = sorted(p.stem for p in NOTEBOOK_DIR.glob("*.ipynb"))
    assert present == EXPECTED


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
