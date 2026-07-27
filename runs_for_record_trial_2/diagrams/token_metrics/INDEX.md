# Trial 2 token-metric diagrams

These figures use only the 92 finalized `record.json` files. The generator does
not read conversation logs, traces, exploit source, payloads, or target
binaries, and it does not execute any submission.

## Headline token accounting

- Aggregate total tokens: 32,299,144.
- Aggregate prompt tokens: 30,672,069 (95.0%).
- Aggregate completion tokens: 1,627,075 (5.0%).
- Median total tokens for successes: 155,718.
- Median total tokens for failures: 508,466.
- Pearson correlation between iterations and total tokens: 0.813.

The association between high token use and failure must not be interpreted as
showing that tokens cause failure. Hard or stalled trajectories both consume
more iterations and are more likely to exhaust the budget.

## Figures

1. **Termination modes** — successful trajectories generally terminate well
   below the budget, while token-budget failures cluster at and just beyond it.

   ![Total-token distribution by termination mode](01_tokens_by_termination.png)

2. **Backend distributions** — the individual-run overlay exposes within-model
   heterogeneity and budget pileups hidden by a median alone.

   ![Total-token distribution by backend](02_tokens_by_backend.png)

3. **Strategy distributions** — ReAct has the largest unadjusted median, but the
   three distributions overlap substantially and combine different backend and
   target mixtures.

   ![Total-token distribution by prompting strategy](03_tokens_by_strategy.png)

4. **Backend × target heatmap** — median demand and success should be read
   together because a high median may indicate a difficult or unresolved cell.

   ![Median total tokens by backend and target](04_backend_target_token_heatmap.png)

5. **Prompt/completion composition** — prompt tokens dominate every backend,
   consistent with repeated context and tool output rather than unusually long
   model completions being the principal token cost.

   ![Prompt and completion composition](05_prompt_completion_composition.png)

6. **Tokens versus iterations** — total tokens rise strongly with turn count;
   the relationship is descriptive and partly mechanical because accumulated
   context is reintroduced across iterations.

   ![Total tokens versus iterations](06_tokens_vs_iterations.png)

7. **Aggregate expenditure and yield** — GPT-OSS consumed the most aggregate
   tokens despite only three successes. Ratios are workload-level summaries and
   are undefined for backends with no observed success.

   ![Aggregate token expenditure and success yield](07_token_expenditure_and_yield.png)

## Reproduction

Run `python3 ../generate_token_metric_diagrams.py` from this directory, or run
the generator from the repository root. It creates the editable SVG sources;
the PNG files are rendered counterparts for document use.
