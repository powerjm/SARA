# Cross-trial token metrics — trial-specific premium models

Only finalized `record.json` metadata is used. The trials have different
model, target, prompting, tool, and resource compositions; these are
descriptive workload metrics rather than isolated efficiency effects.

## Headline accounting

- Trial 1: n=553; total=53,816,714; prompt share=87.7%; median=63,895; iteration-token r=0.918.
- Trial 2: n=46; total=13,376,544; prompt share=95.4%; median=260,376; iteration-token r=0.898.
- Trial 3: n=108; total=21,634,417; prompt share=93.8%; median=150,305; iteration-token r=0.930.

## Figures

1. ![Tokens by termination](01_tokens_by_termination.png)
2. ![Tokens by backend](02_tokens_by_backend.png)
3. ![Tokens by strategy](03_tokens_by_strategy.png)
4. ![Backend target token heatmap](04_backend_target_token_heatmap.png)
5. ![Prompt completion composition](05_prompt_completion_composition.png)
6. ![Tokens versus iterations](06_tokens_vs_iterations.png)
7. ![Token expenditure and yield](07_token_expenditure_and_yield.png)

Figure 6 uses Trial 1 circles, Trial 2 squares, and Trial 3
triangles. Success, token-budget, wall-clock, and truncated
records retain the Trial 2 color palette; refusal/other records
are slate so that every premium run remains represented. The
dashed quadratic curve is an illustrative least-squares reference.

## Tables

- [Markdown tables](TOKEN_TABLES.md)
- [Rendered table diagrams](table_diagrams/INDEX.md)
- CSV tables are in [`tables/`](tables/).

## Reproduction

Run `python3 compare_all_trials/generate_token_metric_packages.py` from
the repository root.
