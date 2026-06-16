"""Statistical analysis pipeline.

Two submodules:
    - stats:      the bare test implementations (Cochran's Q, McNemar's, ...).
    - aggregate:  collapses raw run records into the matrices stats consumes.

Notebooks under analysis/notebooks/ drive these end-to-end.
"""

from analysis.aggregate import (
    CellSummary,
    aggregate_runs,
    build_metric_matrix,
    build_outcome_matrix,
)
from analysis.stats import (
    CochranQResult,
    FriedmanResult,
    McNemarResult,
    WilcoxonResult,
    WilsonCI,
    bonferroni_alpha,
    cochrans_q,
    friedman,
    mcnemar_exact,
    pairwise_labels,
    wilcoxon_signed_rank,
    wilson_ci,
)

__all__ = [
    "CellSummary",
    "CochranQResult",
    "FriedmanResult",
    "McNemarResult",
    "WilcoxonResult",
    "WilsonCI",
    "aggregate_runs",
    "bonferroni_alpha",
    "build_metric_matrix",
    "build_outcome_matrix",
    "cochrans_q",
    "friedman",
    "mcnemar_exact",
    "pairwise_labels",
    "wilcoxon_signed_rank",
    "wilson_ci",
]
