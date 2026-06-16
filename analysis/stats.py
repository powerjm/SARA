"""
Statistical analysis module.

Implements the inference plan from the Scientific Method Worksheet:

  * Cochran's Q              — omnibus across all backends on binary outcomes.
  * McNemar's (exact)        — pairwise follow-up on outcomes.
  * Friedman's               — omnibus across backends on time / cost / iteration.
  * Wilcoxon signed-rank     — pairwise follow-up on time / cost.
  * Wilson score interval    — small-n confidence intervals for success rates.
  * Bonferroni correction    — applied at the call site, helper provided here.
  * Effect sizes             — Cohen's g, Kendall's W, matched-pairs r.

Inputs are paired-by-binary matrices: rows are binaries, columns are backends.
For outcomes, cells are 0/1 (success / non-success). For time/cost/iterations,
cells are real-valued. NaN cells are not supported — see `aggregate_runs` for
the canonical collapsing rule when N>1 runs per cell.

All functions return plain dataclasses so the analysis notebooks can format
without importing scipy types directly.

References
----------
- Cochran, W. G. (1950). The comparison of percentages in matched samples.
  Biometrika 37(3/4): 256-266.
- McNemar, Q. (1947). Note on the sampling error of the difference between
  correlated proportions or percentages. Psychometrika 12(2): 153-157.
- Friedman, M. (1937). The use of ranks to avoid the assumption of normality
  implicit in the analysis of variance. JASA 32(200): 675-701.
- Wilcoxon, F. (1945). Individual comparisons by ranking methods.
  Biometrics Bulletin 1(6): 80-83.
- Wilson, E. B. (1927). Probable inference, the law of succession, and
  statistical inference. JASA 22(158): 209-212.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

# --------------------------------------------------------------------------- #
# Result dataclasses                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CochranQResult:
    """Cochran's Q omnibus test result."""

    statistic: float
    df: int
    p_value: float
    k: int  # number of conditions (backends)
    n: int  # number of subjects (binaries)


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """Pairwise McNemar's test (exact binomial form for small n)."""

    backend_a: str
    backend_b: str
    b: int  # A success, B failure
    c: int  # A failure, B success
    statistic: float
    p_value: float
    method: str  # "exact_binomial" | "chi_squared_continuity"
    cohens_g: float  # effect size: (b - c) / (2 (b + c)); 0 = no asymmetry


@dataclass(frozen=True, slots=True)
class FriedmanResult:
    """Friedman omnibus test result."""

    statistic: float
    df: int
    p_value: float
    k: int
    n: int
    kendalls_w: float  # effect size, [0, 1]


@dataclass(frozen=True, slots=True)
class WilcoxonResult:
    """Wilcoxon signed-rank pairwise test."""

    backend_a: str
    backend_b: str
    statistic: float
    p_value: float
    method: str  # "exact" | "approx"
    rank_biserial_r: float


@dataclass(frozen=True, slots=True)
class WilsonCI:
    """Wilson score interval for a single proportion."""

    backend: str
    successes: int
    n: int
    proportion: float
    ci_low: float
    ci_high: float
    confidence: float


# --------------------------------------------------------------------------- #
# Cochran's Q                                                                 #
# --------------------------------------------------------------------------- #


def cochrans_q(outcomes: Sequence[Sequence[int]]) -> CochranQResult:
    """
    Cochran's Q test on a (n_binaries x k_backends) 0/1 matrix.

    H0: success rates are equal across all backends (within-subject).

    Formula:
        Q = (k - 1) * (k * sum(C_j^2) - T^2) / (k * T - sum(R_i^2))

    where:
        T       = grand total of successes
        C_j     = column totals (per backend)
        R_i     = row totals (per binary)
        k       = number of backends
        n       = number of binaries

    Q ~ chi-squared with df = k - 1 under H0.
    """
    from scipy.stats import chi2  # type: ignore[import-not-found]

    n = len(outcomes)
    if n == 0:
        raise ValueError("empty outcomes matrix")
    k = len(outcomes[0])
    if k < 2:
        raise ValueError("Cochran's Q requires k >= 2 conditions")
    for row in outcomes:
        if len(row) != k:
            raise ValueError("ragged outcomes matrix")
        for cell in row:
            if cell not in (0, 1):
                raise ValueError(f"non-binary cell: {cell!r}")

    col_totals = [sum(row[j] for row in outcomes) for j in range(k)]
    row_totals = [sum(row) for row in outcomes]
    T = sum(col_totals)

    denom = k * T - sum(r * r for r in row_totals)
    if denom == 0:
        # All binaries either all-success or all-failure: Q undefined; conventionally 0.
        return CochranQResult(statistic=0.0, df=k - 1, p_value=1.0, k=k, n=n)

    q = (k - 1) * (k * sum(c * c for c in col_totals) - T * T) / denom
    p = float(chi2.sf(q, df=k - 1))
    return CochranQResult(statistic=float(q), df=k - 1, p_value=p, k=k, n=n)


# --------------------------------------------------------------------------- #
# McNemar's (exact)                                                           #
# --------------------------------------------------------------------------- #


def mcnemar_exact(
    outcomes_a: Sequence[int],
    outcomes_b: Sequence[int],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> McNemarResult:
    """
    Exact-binomial McNemar's test for paired binary outcomes.

    Counts:
        b = trials where A succeeded and B failed
        c = trials where A failed   and B succeeded

    Test statistic (chi-squared with continuity, recorded for reference) is
    less accurate than the exact binomial when (b + c) < 25, so this function
    always reports the exact binomial p-value.
    """
    from scipy.stats import binomtest  # type: ignore[import-not-found]

    if len(outcomes_a) != len(outcomes_b):
        raise ValueError("paired vectors must have equal length")

    b = sum(1 for a, x in zip(outcomes_a, outcomes_b, strict=True) if a == 1 and x == 0)
    c = sum(1 for a, x in zip(outcomes_a, outcomes_b, strict=True) if a == 0 and x == 1)

    n_disc = b + c
    if n_disc == 0:
        # No discordant pairs: the test is undefined; return p=1.0.
        return McNemarResult(
            backend_a=label_a,
            backend_b=label_b,
            b=b,
            c=c,
            statistic=0.0,
            p_value=1.0,
            method="exact_binomial",
            cohens_g=0.0,
        )

    # Two-sided exact binomial against p=0.5.
    result = binomtest(k=min(b, c), n=n_disc, p=0.5, alternative="two-sided")
    p = float(result.pvalue)
    # Continuity-corrected chi-squared for reference (not used for p):
    stat = ((abs(b - c) - 1) ** 2) / n_disc if n_disc > 0 else 0.0
    g = (b - c) / (2.0 * n_disc)
    return McNemarResult(
        backend_a=label_a,
        backend_b=label_b,
        b=b,
        c=c,
        statistic=float(stat),
        p_value=p,
        method="exact_binomial",
        cohens_g=g,
    )


# --------------------------------------------------------------------------- #
# Friedman's                                                                  #
# --------------------------------------------------------------------------- #


def friedman(values: Sequence[Sequence[float]]) -> FriedmanResult:
    """
    Friedman test on a (n_binaries x k_backends) numeric matrix.

    Within each binary (row), backends are ranked, then column rank totals
    are tested. Use this for time, cost, or iteration count comparisons
    where the response is continuous-valued.

    Kendall's W is reported as the effect size, in [0, 1].
    """
    from scipy.stats import friedmanchisquare  # type: ignore[import-not-found]

    n = len(values)
    if n == 0:
        raise ValueError("empty values matrix")
    k = len(values[0])
    if k < 2:
        raise ValueError("Friedman requires k >= 2 conditions")
    columns = [[row[j] for row in values] for j in range(k)]
    stat, p = friedmanchisquare(*columns)
    # Kendall's W from the chi-squared statistic.
    w = float(stat) / (n * (k - 1)) if n > 0 and k > 1 else 0.0
    return FriedmanResult(
        statistic=float(stat),
        df=k - 1,
        p_value=float(p),
        k=k,
        n=n,
        kendalls_w=w,
    )


# --------------------------------------------------------------------------- #
# Wilcoxon signed-rank                                                        #
# --------------------------------------------------------------------------- #


def wilcoxon_signed_rank(
    values_a: Sequence[float],
    values_b: Sequence[float],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> WilcoxonResult:
    """
    Wilcoxon signed-rank pairwise test.

    Uses scipy's `exact` mode for small n, where the normal approximation
    is unreliable. Reports matched-pairs rank-biserial r as the effect size.
    """
    from scipy.stats import wilcoxon  # type: ignore[import-not-found]

    if len(values_a) != len(values_b):
        raise ValueError("paired vectors must have equal length")

    diffs = [a - b for a, b in zip(values_a, values_b, strict=True)]
    nonzero = [d for d in diffs if d != 0]
    if not nonzero:
        return WilcoxonResult(
            backend_a=label_a,
            backend_b=label_b,
            statistic=0.0,
            p_value=1.0,
            method="exact",
            rank_biserial_r=0.0,
        )

    method = "exact" if len(nonzero) <= 25 else "approx"
    res = wilcoxon(values_a, values_b, method=method, zero_method="wilcox")
    # rank-biserial r from signed ranks: (W+ - W-) / (W+ + W-)
    ranks_pos = sum(abs(d) for d in nonzero if d > 0)
    ranks_neg = sum(abs(d) for d in nonzero if d < 0)
    total = ranks_pos + ranks_neg
    r = (ranks_pos - ranks_neg) / total if total else 0.0

    return WilcoxonResult(
        backend_a=label_a,
        backend_b=label_b,
        statistic=float(res.statistic),
        p_value=float(res.pvalue),
        method=method,
        rank_biserial_r=float(r),
    )


# --------------------------------------------------------------------------- #
# Wilson score interval                                                       #
# --------------------------------------------------------------------------- #


def wilson_ci(
    successes: int,
    n: int,
    *,
    confidence: float = 0.95,
    backend: str = "",
) -> WilsonCI:
    """
    Wilson score interval for a single proportion.

    Preferred over the Wald interval for small n because it never produces
    bounds outside [0, 1] and has better coverage near 0 or 1.

    Formula:
        p~  = (x + z^2/2) / (n + z^2)
        CI  = p~ +/- (z / (n + z^2)) * sqrt(x(n-x)/n + z^2/4)
    """
    from scipy.stats import norm  # type: ignore[import-not-found]

    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes out of range")

    z = float(norm.ppf(1 - (1 - confidence) / 2))
    p_hat = successes / n
    centre = (successes + z * z / 2) / (n + z * z)
    half = (z / (n + z * z)) * math.sqrt(successes * (n - successes) / n + z * z / 4)
    return WilsonCI(
        backend=backend,
        successes=successes,
        n=n,
        proportion=p_hat,
        ci_low=max(0.0, centre - half),
        ci_high=min(1.0, centre + half),
        confidence=confidence,
    )


# --------------------------------------------------------------------------- #
# Bonferroni helper                                                            #
# --------------------------------------------------------------------------- #


def bonferroni_alpha(alpha: float, n_comparisons: int) -> float:
    """Bonferroni-adjusted alpha: alpha / m. For k=3 backends, m=3, so 0.0167."""
    if n_comparisons <= 0:
        raise ValueError("n_comparisons must be positive")
    return alpha / n_comparisons


def pairwise_labels(labels: Sequence[str]) -> list[tuple[str, str]]:
    """All unordered backend pairs, in stable order."""
    return list(combinations(labels, 2))


__all__ = [
    "CochranQResult",
    "FriedmanResult",
    "McNemarResult",
    "WilcoxonResult",
    "WilsonCI",
    "bonferroni_alpha",
    "cochrans_q",
    "friedman",
    "mcnemar_exact",
    "pairwise_labels",
    "wilcoxon_signed_rank",
    "wilson_ci",
]
