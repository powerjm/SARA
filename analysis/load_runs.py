"""
Load run records for the analysis notebooks.

The notebooks are thin orchestrators; the reusable, unit-testable plumbing lives
here:

  * :func:`load_all` — read every finalized ``record.json`` under the run output
    directory, falling back to the deterministic synthetic dataset
    (``analysis.synthetic``) when no real runs exist yet, so the whole analysis
    pipeline and ``make notebooks`` run before the first agent run.
  * :func:`backend_names` / :func:`strategies` — the axes of the matrix.
  * :func:`difficulty_tier` — map a ``binary_id`` to its tier (manifest first,
    then the synthetic ``syn-bin-NN`` convention) so notebooks can do the
    within-tier and across-tier breakdowns (Step-6 decision).
  * :func:`pin_style` / :func:`save_figure` — pin matplotlib + RNG seeds and
    write figures under ``analysis/figures/<stem>/`` for reproducibility.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from analysis import synthetic
from harness import persistence
from harness.record import RunRecord

if TYPE_CHECKING:
    from matplotlib.figure import Figure

_REPO_ROOT = Path(__file__).resolve().parent.parent
FIGURES_ROOT = _REPO_ROOT / "analysis" / "figures"

# Default seed used everywhere a figure or the synthetic fallback needs one, so
# notebook outputs are byte-stable across runs.
DEFAULT_SEED = 0

_SYN_BIN = re.compile(r"^syn-bin-(\d+)$")


def runs_dir() -> Path:
    """The run output directory, honoring ``RUN_OUTPUT_DIR`` (default ``runs/``)."""
    return Path(os.environ.get("RUN_OUTPUT_DIR", str(_REPO_ROOT / "runs")))


def load_all(
    directory: Path | None = None,
    *,
    fallback_synthetic: bool = True,
    seed: int = DEFAULT_SEED,
    replicates: int = 5,
) -> list[RunRecord]:
    """Load every finalized run record, or the synthetic dataset if none exist.

    Returns the synthetic dataset (deterministic for ``seed``) when no real runs
    are present and ``fallback_synthetic`` is set — this is what lets the
    notebooks render before any agent run has happened.
    """
    directory = directory or runs_dir()
    records = list(persistence.iter_records(directory))
    if records:
        return records
    if fallback_synthetic:
        return synthetic.generate(seed=seed, replicates=replicates)
    return []


def backend_names(records: list[RunRecord]) -> list[str]:
    """Sorted unique backend names present in ``records``."""
    return sorted({r.backend.name for r in records})


def strategies(records: list[RunRecord]) -> list[str]:
    """Sorted unique prompting strategies present in ``records``."""
    return sorted({str(r.prompting_strategy) for r in records})


def category_of(records: list[RunRecord]) -> dict[str, str]:
    """Map each backend name to its (single) declared category."""
    return {r.backend.name: str(r.backend.category) for r in records}


def difficulty_tier(binary_id: str) -> int | None:
    """The difficulty tier of a binary: manifest first, else ``syn-bin-NN`` mod 4.

    The synthetic generator assigns ``difficulty = index % 4`` to ``syn-bin-NN``;
    real binaries carry ``difficulty_tier`` in the corpus manifest.
    """
    match = _SYN_BIN.match(binary_id)
    if match:
        return int(match.group(1)) % 4
    try:
        from harness import corpus

        return corpus.resolve_binary(binary_id, require_file=False).difficulty_tier
    except Exception:
        return None


def tiers(records: list[RunRecord]) -> list[int]:
    """Sorted unique difficulty tiers represented in ``records``."""
    found = {difficulty_tier(r.binary_id) for r in records}
    return sorted(t for t in found if t is not None)


# --------------------------------------------------------------------------- #
# Figure helpers                                                              #
# --------------------------------------------------------------------------- #


def pin_style(seed: int = DEFAULT_SEED) -> Any:
    """Pin matplotlib (Agg, fixed rcParams) and RNG seeds; return ``pyplot``.

    Called once at the top of every notebook so figures are deterministic and
    render headlessly under ``jupyter nbconvert --execute``.
    """
    import random

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update(
        {
            "figure.figsize": (8, 5),
            "figure.dpi": 120,
            "savefig.dpi": 120,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "font.size": 11,
            "axes.titlesize": 13,
            "svg.hashsalt": "sara",
        }
    )
    random.seed(seed)
    np.random.seed(seed)
    return plt


def figures_dir(stem: str) -> Path:
    """Ensure and return ``analysis/figures/<stem>/``."""
    out = FIGURES_ROOT / stem
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_figure(fig: Figure, stem: str, name: str) -> Path:
    """Save ``fig`` as a PNG under ``analysis/figures/<stem>/<name>.png``."""
    path = figures_dir(stem) / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    return path


__all__ = [
    "DEFAULT_SEED",
    "FIGURES_ROOT",
    "backend_names",
    "category_of",
    "difficulty_tier",
    "figures_dir",
    "load_all",
    "pin_style",
    "runs_dir",
    "save_figure",
    "strategies",
    "tiers",
]
