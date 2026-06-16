"""Tests for analysis.stats.

These tests pin the basic correctness of each statistical helper using
small fixtures with known answers. They are not a replacement for the
notebooks' analytic validation but they catch regressions in the wrapping
of scipy/statsmodels calls.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("scipy")  # skip whole module if scipy isn't installed

from analysis.stats import (
    bonferroni_alpha,
    cochrans_q,
    friedman,
    mcnemar_exact,
    pairwise_labels,
    wilcoxon_signed_rank,
    wilson_ci,
)

# --------------------------------------------------------------------------- #
# Cochran's Q                                                                  #
# --------------------------------------------------------------------------- #


def test_cochrans_q_basic_shape() -> None:
    # 5 binaries x 3 backends. Backend C clearly best (4/5), A worst (1/5).
    outcomes = [
        [0, 1, 1],
        [0, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
        [0, 1, 0],
    ]
    res = cochrans_q(outcomes)
    assert res.k == 3
    assert res.n == 5
    assert res.df == 2
    assert 0.0 <= res.p_value <= 1.0
    assert res.statistic >= 0.0


def test_cochrans_q_rejects_non_binary() -> None:
    with pytest.raises(ValueError, match="non-binary"):
        cochrans_q([[0, 1, 2], [0, 1, 0]])


def test_cochrans_q_rejects_ragged() -> None:
    with pytest.raises(ValueError, match="ragged"):
        cochrans_q([[0, 1], [0, 1, 0]])


def test_cochrans_q_all_same_returns_p1() -> None:
    # Every backend has the same outcome on every binary -> denominator = 0 -> Q=0, p=1.
    outcomes = [[1, 1, 1], [0, 0, 0], [1, 1, 1]]
    res = cochrans_q(outcomes)
    assert res.statistic == 0.0
    assert res.p_value == 1.0


# --------------------------------------------------------------------------- #
# McNemar's                                                                    #
# --------------------------------------------------------------------------- #


def test_mcnemar_exact_no_discordant_pairs() -> None:
    a = [1, 0, 1, 0]
    b = [1, 0, 1, 0]
    res = mcnemar_exact(a, b, label_a="x", label_b="y")
    assert res.b == 0
    assert res.c == 0
    assert res.p_value == 1.0
    assert res.cohens_g == 0.0


def test_mcnemar_exact_counts_discordant_correctly() -> None:
    # A succeeds on 1,2,3; B succeeds on 1,4 -> b=2 (2,3), c=1 (4)
    a = [1, 1, 1, 0]
    b = [1, 0, 0, 1]
    res = mcnemar_exact(a, b)
    assert res.b == 2
    assert res.c == 1


def test_mcnemar_exact_rejects_unequal_lengths() -> None:
    with pytest.raises(ValueError, match="equal length"):
        mcnemar_exact([1, 0], [1, 0, 1])


# --------------------------------------------------------------------------- #
# Friedman's                                                                   #
# --------------------------------------------------------------------------- #


def test_friedman_basic_shape() -> None:
    # 5 binaries x 3 backends. Backend C is always fastest.
    values = [
        [10.0, 8.0, 4.0],
        [12.0, 9.0, 5.0],
        [9.0, 7.0, 3.0],
        [11.0, 8.0, 5.0],
        [10.0, 9.0, 4.0],
    ]
    res = friedman(values)
    assert res.k == 3
    assert res.n == 5
    assert res.df == 2
    assert 0.0 <= res.kendalls_w <= 1.0


# --------------------------------------------------------------------------- #
# Wilcoxon                                                                     #
# --------------------------------------------------------------------------- #


def test_wilcoxon_signed_rank_zero_diffs() -> None:
    a = [5.0, 5.0, 5.0]
    b = [5.0, 5.0, 5.0]
    res = wilcoxon_signed_rank(a, b)
    assert res.p_value == 1.0
    assert res.rank_biserial_r == 0.0


def test_wilcoxon_signed_rank_one_sided_effect() -> None:
    a = [10.0, 12.0, 11.0, 9.0]
    b = [5.0, 6.0, 4.0, 7.0]
    res = wilcoxon_signed_rank(a, b)
    # A is uniformly larger; rank-biserial r should be positive.
    assert res.rank_biserial_r > 0


# --------------------------------------------------------------------------- #
# Wilson CI                                                                    #
# --------------------------------------------------------------------------- #


def test_wilson_ci_within_zero_one() -> None:
    res = wilson_ci(successes=3, n=10, backend="claude-sonnet")
    assert 0.0 <= res.ci_low <= res.proportion <= res.ci_high <= 1.0


def test_wilson_ci_zero_successes() -> None:
    # x=0: lower bound at 0, upper bound > 0.
    res = wilson_ci(successes=0, n=10)
    assert res.ci_low == 0.0
    assert res.ci_high > 0.0


def test_wilson_ci_all_successes() -> None:
    res = wilson_ci(successes=10, n=10)
    assert res.ci_high == 1.0
    assert res.ci_low < 1.0


def test_wilson_ci_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        wilson_ci(successes=-1, n=10)
    with pytest.raises(ValueError):
        wilson_ci(successes=11, n=10)
    with pytest.raises(ValueError):
        wilson_ci(successes=1, n=0)


# --------------------------------------------------------------------------- #
# Bonferroni / pairwise helpers                                                #
# --------------------------------------------------------------------------- #


def test_bonferroni_alpha_three_pairs() -> None:
    assert math.isclose(bonferroni_alpha(0.05, 3), 0.05 / 3)


def test_bonferroni_alpha_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        bonferroni_alpha(0.05, 0)


def test_pairwise_labels_three_backends() -> None:
    pairs = pairwise_labels(["premium", "open_weight", "unrestricted"])
    assert len(pairs) == 3
    assert ("premium", "open_weight") in pairs
