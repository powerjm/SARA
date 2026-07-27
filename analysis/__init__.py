# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

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
    build_tier_matrix,
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
    "build_tier_matrix",
    "cochrans_q",
    "friedman",
    "mcnemar_exact",
    "pairwise_labels",
    "wilcoxon_signed_rank",
    "wilson_ci",
]
