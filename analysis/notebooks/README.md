# analysis/notebooks/

Jupyter notebooks that drive the statistical pipeline end-to-end. Each notebook is a thin orchestrator that:

1. Loads `runs/*/record.json` into a list of `RunRecord` instances.
2. Calls `analysis.aggregate.aggregate_runs(...)` to collapse to cells.
3. Calls the appropriate test from `analysis.stats`.
4. Renders tables and figures into `analysis/figures/`.

The **notebook sources are committed** (they are the Step-6 deliverable) and are
kept output-free — `make notebooks` re-executes them. The generated figures
(`analysis/figures/`) and executed copies (`build/notebooks/`) are gitignored
build output; commit nbconvert HTML exports under `docs/analysis_html/` for the
thesis appendix if needed.

Shared plumbing lives in `analysis/load_runs.py` (`load_all`, axis helpers,
`difficulty_tier`, `pin_style`, `save_figure`) so each notebook stays a thin
orchestrator: load → `aggregate_runs` → an `analysis.stats` test → a figure → a
copy-pasteable Markdown summary. Until real runs exist, `load_all()` falls back
to the deterministic synthetic dataset (`analysis.synthetic`), so the whole
pipeline runs reproducibly today.

## The seven notebooks

| Notebook | Drives |
|----------|--------|
| `01_outcome_omnibus.ipynb` | Cochran's Q across backends; within-/across-tier success |
| `02_outcome_pairwise.ipynb` | McNemar's exact, Bonferroni-corrected |
| `03_time_cost_omnibus.ipynb` | Friedman's on wall-clock and USD cost |
| `04_time_cost_pairwise.ipynb` | Wilcoxon signed-rank, Bonferroni-corrected |
| `05_success_intervals.ipynb` | Wilson score CIs per backend |
| `06_failure_mode_crosstab.ipynb` | FailureMode by backend category + refusal CIs |
| `07_strategy_effect.ipynb` | Prompting strategy as factor (Cochran's Q) |

## Running

```bash
make notebooks                       # execute all seven headlessly (CI-safe)
source .venv/bin/activate && jupyter lab analysis/notebooks   # interactive
```
