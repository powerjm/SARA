# analysis/

The inference layer. It turns raw per-run records into the statistics the thesis
reports. Data flows in **one direction** — nothing here runs an agent, executes a
payload, or mutates a record:

```
runs/*/record.json                     (one RunRecord per run — the schema is the contract)
        │  load_runs.load_all()
        ▼
   list[RunRecord]
        │  aggregate.aggregate_runs()          collapse N replicates → one cell
        ▼
   list[CellSummary]                    one per (binary, backend, strategy)
        │  aggregate.build_outcome_matrix()    paired-by-binary 0/1 matrix
        │  aggregate.build_metric_matrix()     paired-by-binary real matrix
        ▼
   matrices (rows = binaries, cols = backends)
        │  analysis.stats.*                     omnibus + pairwise tests, effect sizes, CIs
        ▼
   result dataclasses  →  notebooks/  →  tables + figures/  →  thesis Findings
```

The canonical schema for a `RunRecord` lives in [`../harness/record.py`](../harness/record.py);
every field consumed here is defined there. If a field changes, that is a
`schema_version` event — this module reads through the same Pydantic models, so
it inherits the migration behavior automatically.

## Module map

| Module | Responsibility |
|--------|----------------|
| [`load_runs.py`](load_runs.py) | Load finalized records (or the deterministic synthetic fallback); expose the matrix axes (`backend_names`, `strategies`, `tiers`); pin matplotlib + RNG seeds and save figures. |
| [`aggregate.py`](aggregate.py) | Collapse replicate runs into `CellSummary`; build the paired outcome / metric matrices; extract per-binary success chains. |
| [`stats.py`](stats.py) | The statistical tests, effect sizes, confidence intervals, and the chain-uniqueness metric. Pure functions returning plain dataclasses. |
| [`synthetic.py`](synthetic.py) | Deterministic synthetic `RunRecord` generator — byte-identical for a fixed seed, exercises every `Outcome` and `FailureMode` — so the whole pipeline runs before the first real agent run. |
| [`notebooks/`](notebooks/) | Seven thin orchestrators (load → aggregate → one test → figure → summary). See [`notebooks/README.md`](notebooks/README.md). |

## The unit of analysis: the cell

The experiment is a matrix of `(binary, backend, prompting_strategy)` triples,
each run **N ≥ 1** times to absorb backend stochasticity. `aggregate_runs`
collapses each triple's replicates into one `CellSummary` using fixed rules:

- **Outcome (binary).** A cell is a **success (1) iff _any_ replicate succeeded** —
  a spawned shell printed the universal marker ([ADR 0009](../docs/adr/0009-shell-success-marker.md)).
  This is a *capability* framing ("can this backend ever solve this binary?"),
  not an average success rate. It is deliberately N-dependent: more replicates can
  only raise a cell's success probability, so **N must be held constant across
  cells** for cells to be comparable.
- **Refusal.** `refused_all` is true iff *every* replicate was a
  `SAFEGUARD_REFUSAL`. This is tracked separately from success/failure because a
  policy refusal ("wouldn't") is a qualitatively different event from a mechanical
  failure ("couldn't") — see the missing-data policy below.
- **Time / cost / iterations (continuous).** The cell value is the **median**
  across replicates, to dampen outliers. Note the median is taken over *all*
  replicates regardless of outcome (see Limitations).

## Missing-data policy

The outcome and metric matrices are **paired by binary**: every statistical test
here assumes each binary contributes one aligned row across the backends being
compared. Two rules keep that pairing honest:

1. **Refusals are excluded, not scored as failures.**
   `build_outcome_matrix` treats an all-refused cell (`refused_all`) as *missing*
   rather than as a `0`. Counting a refusal as a mechanical failure would conflate
   "the model declined on policy grounds" with "the model tried and could not build
   the chain" — the exact distinction the experiment exists to measure. (A cell
   with a *mix* of refusals and genuine attempts is **not** `refused_all`, so it
   still scores as a real `0`: there was an attempt, and it failed.)

2. **Incomplete binaries are dropped (complete-case analysis).**
   If any backend in the requested set has no scorable cell for a binary — never
   run, or all-refused — that binary is dropped from the matrix entirely. This
   yields a fully paired matrix with no gaps, so Cochran's Q / Friedman receive
   valid input and the pairwise columns derived from the same matrix stay aligned.
   The returned `binary_ids` is the surviving (complete-case) set, and the
   notebooks report `n = len(binary_ids)`, so any reduction in `n` is visible in
   the output rather than hidden.

   *Consequence:* because the notebooks derive the pairwise columns from the shared
   matrix, a third backend refusing on a binary also removes that binary from the
   two-backend comparisons. This trades statistical power for a single consistent
   binary set across the omnibus and every pairwise follow-up.

The metric matrix previously filled a missing cell with `NaN`, which silently
propagated to a `NaN` omnibus statistic; the drop rule replaces that failure mode.

## The tests

All tests are **nonparametric** and **within-subject** (paired by binary): success
rates and run times are neither normal nor independent across backends solving the
same binary, so ranks and exact distributions are used throughout. The plan mirrors
the Scientific Method Worksheet — an omnibus test first, then Bonferroni-corrected
pairwise follow-ups only if the omnibus rejects.

### Binary outcomes (success / non-success)

| Purpose | Function | H0 | Notes |
|---------|----------|----|-------|
| Omnibus across backends | `cochrans_q` | success rate equal across all backends | Q ~ χ² with df = k − 1; the binary-outcome analogue of a repeated-measures ANOVA. Degenerate all-same matrices return Q = 0, p = 1. |
| Pairwise follow-up | `mcnemar_exact` | the two discordant cells are equally likely | Exact binomial on the discordant pairs (b, c) — correct for the small, sparse tables here, where the χ² approximation is unreliable. Effect size: **Cohen's g** = (b − c) / 2(b + c), signed to show direction. |
| Per-backend interval | `wilson_ci` | — | Wilson score interval for each backend's success proportion. Preferred over Wald at small n: bounds never leave [0, 1] and coverage is better near 0 or 1. Notebook 05 uses n = number of (complete-case) binaries. |

### Continuous metrics (wall-clock, USD cost, iterations)

| Purpose | Function | H0 | Notes |
|---------|----------|----|-------|
| Omnibus across backends | `friedman` | metric distribution equal across backends | Ranks backends within each binary, tests the rank totals. Effect size: **Kendall's W** ∈ [0, 1] (0 = no agreement in rankings, 1 = perfect). |
| Pairwise follow-up | `wilcoxon_signed_rank` | median paired difference is zero | Uses scipy's `exact` distribution for ≤ 25 non-zero differences, the normal approximation above that. Effect size: **matched-pairs rank-biserial r** = (W⁺ − W⁻)/(W⁺ + W⁻), computed from the **ranks** of the absolute differences (ties take average ranks). |

### Descriptive summaries (no null hypothesis)

- **Failure-mode crosstab** (notebook 06): `FailureMode` counts by backend
  category, with a Wilson interval on each category's refusal rate.
- **Chain uniqueness** (`chain_uniqueness`, notebook via `collect_success_chains`):
  repurposes the [ADR 0003](../docs/adr/0003-chain-fingerprint.md) chain
  fingerprint to describe, per binary, how many *distinct* working exploits exist
  across backends and how many were found by exactly one backend ([ADR 0009](../docs/adr/0009-shell-success-marker.md)).
  Descriptive only — it does not gate success.

## Multiple comparisons

With k = 3 backend categories there are 3 pairwise comparisons per omnibus.
`bonferroni_alpha(0.05, 3)` gives the family-wise-corrected threshold
(α = 0.0167); `pairwise_labels` enumerates the pairs in stable order. Correction
is applied **at the call site** in notebooks 02 and 04 so the correction count is
explicit and visible next to the results it governs.

## Reproducibility

- **Seeds pinned everywhere.** `load_runs.pin_style(seed=0)` fixes matplotlib
  (Agg backend, fixed rcParams, `svg.hashsalt`) and the `random` / `numpy` RNGs at
  the top of every notebook, so figures are byte-stable.
- **Deterministic synthetic fallback.** When no real runs exist, `load_all()`
  returns `synthetic.generate(seed=…)` — a dataset with no `uuid4()` or
  `datetime.now()`, so the entire pipeline (and `make notebooks`) is reproducible
  today and exercises every enum branch. Real runs, once present, take precedence.
- **Figures** are written under `analysis/figures/<notebook_stem>/` (gitignored
  build output); commit nbconvert HTML exports for the thesis appendix if needed.

## Assumptions & limitations

- **Complete-case pairing.** The paired tests require the same binaries across the
  compared backends; the drop rule enforces this but reduces `n` when data is
  incomplete. Report the surviving `n` alongside every result.
- **N-dependence of the success collapse.** The any-success rule makes a cell's
  success probability rise with the replicate count, so comparisons are only valid
  when N is fixed across cells.
- **Median time/cost mixes outcomes.** A cell's median run time is taken over
  successes, mechanical failures, *and* the refusals that remain in a cell — so the
  Friedman/Wilcoxon time comparisons measure "time to finish, whatever the ending,"
  not "time to a working exploit." Interpret accordingly, or condition on success
  before using the time metric as a difficulty proxy.
- **Wilcoxon exact + ties.** scipy's exact signed-rank distribution assumes no ties
  among the absolute differences; real time/cost data has ties, making that
  p-value approximate at small n.

## Running

```bash
make notebooks        # execute all seven notebooks headlessly (CI-safe)
.venv/bin/pytest tests/test_aggregate.py tests/test_stats.py -q   # unit tests for this module
```
