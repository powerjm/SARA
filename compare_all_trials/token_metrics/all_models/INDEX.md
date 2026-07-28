# Cross-trial token metrics — all finalized models

Only finalized `record.json` metadata is used. The trials have different
model, target, prompting, tool, and resource compositions; these are
descriptive workload metrics rather than isolated efficiency effects.

## Headline accounting

- Trial 1: n=1,755; total=222,905,522; prompt share=90.5%; median=159,126; iteration-token r=0.812.
- Trial 2: n=92; total=32,299,144; prompt share=95.0%; median=424,733; iteration-token r=0.813.
- Trial 3: n=146; total=47,790,128; prompt share=91.8%; median=258,176; iteration-token r=0.858.

## Figures

1. ![Tokens by termination](01_tokens_by_termination.png)
2. ![Tokens by backend](02_tokens_by_backend.png)
3. ![Tokens by strategy](03_tokens_by_strategy.png)
4. ![Backend target token heatmap](04_backend_target_token_heatmap.png)
5. ![Prompt completion composition](05_prompt_completion_composition.png)
6. ![Tokens versus iterations](06_tokens_vs_iterations.png)
7. ![Token expenditure and yield](07_token_expenditure_and_yield.png)

## Tables

- [Markdown tables](TOKEN_TABLES.md)
- [Rendered table diagrams](table_diagrams/INDEX.md)
- CSV tables are in [`tables/`](tables/).

## Reproduction

Run `python3 compare_all_trials/generate_token_metric_packages.py` from
the repository root.
