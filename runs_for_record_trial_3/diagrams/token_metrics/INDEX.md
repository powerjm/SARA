# Trial 3 token-metric diagrams

These figures use only the 146 finalized `record.json` files. No conversations,
traces, exploit source, payloads, target binaries, or submissions are opened.

## Headline token accounting

- Aggregate total tokens: 47,790,128.
- Aggregate prompt tokens: 43,855,890 (91.8%).
- Aggregate completion tokens: 3,934,238 (8.2%).
- Median total tokens for successes: 112,599.
- Median total tokens for nonsuccesses: 339,848.
- Pearson correlation between iterations and total tokens: 0.858.

High token use must not be interpreted as causing failure. Difficult or stalled
trajectories both run longer and are more likely to reach resource limits.

## Figures

1. ![Tokens by termination](01_tokens_by_termination.png)
2. ![Tokens by backend](02_tokens_by_backend.png)
3. ![Tokens by strategy](03_tokens_by_strategy.png)
4. ![Backend-target heatmap](04_backend_target_token_heatmap.png)
5. ![Prompt-completion composition](05_prompt_completion_composition.png)
6. ![Tokens versus iterations](06_tokens_vs_iterations.png)
7. ![Token expenditure and yield](07_token_expenditure_and_yield.png)

The 1,000,000-token line is a soft/checkpointed threshold. Ten finalized records
exceeded it. Backend and target summaries retain Trial 3's structured local
coverage and should not be read as composition-adjusted model efficiency.

## Reproduction

Run `python3 runs_for_record_trial_3/diagrams/generate_token_metric_diagrams.py`
from the repository root.
