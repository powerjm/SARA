# Model provenance by trial (premium backends)

Which model each trial actually ran, reconstructed from the stored `RunRecord`s
(`runs_for_record_trial_{1,2,3}/runs/*/record.json`, field `backend.version`).
This is the per-trial provenance companion to the model-card reference in
[`../backends/README.md`](../backends/README.md).

## What the records store — and what they don't

Every run records the **requested model alias** (`RunRecord.backend.version`),
plus the sampling knobs and the pricing snapshot used to compute cost. The alias
was identical across trials because it is pinned in
[`../backends/registry.py`](../backends/registry.py), which did not change between
runs.

⚠️ **The resolved dated API snapshot was NOT captured.** I checked `record.json`,
`conversation.jsonl`, and `trace.jsonl` for all three trials — none store the
build id the provider resolved the alias to (e.g. `gpt-5-2025-08-07`). Two of the
four premium aliases *float* server-side (`gpt-5`, `gemini-pro-latest`), so the
exact build is only recoverable from the provider console/billing logs for the
run dates below. Document the alias as-run (this file), and if the thesis needs
the precise build, cross-reference the Anthropic/OpenAI dashboards for those dates.

## Per-trial premium roster

| Model (card) | Requested alias | Trial 1 (2026-07-22 → 07-26) | Trial 2 (2026-07-27) | Trial 3 (2026-07-27) |
|---|---|---|---|---|
| Claude Opus 4.7 | `claude-opus-4-7` | ✅ (n=75) | — not run | ✅ (n=36) |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | ✅ (n=95) | ✅ (n=23) | ✅ (n=36) |
| GPT-5 | `gpt-5` | ✅ (n=188) | ✅ (n=23) | ✅ (n=36) |
| Gemini Pro (latest) | `gemini-pro-latest` | ✅ (n=195) | — not run | — not run |

Notes:
- **Opus** was absent from Trial 2 (added to the premium arm for Trial 3).
- **Gemini** ran only in Trial 1; it was dropped from Trials 2 and 3 (it refuses
  this task class almost always — see the card in `backends/README.md`).
- `n` = run count for that backend in that trial (all replicates, all cells).

## Sampling & pricing as recorded (identical across all three trials)

| Model | Vendor / API | Max context (tokens) | temperature (requested) | seed (requested) | Price USD/Mtok (prompt / completion) | Pricing `as_of` |
|---|---|---|---|---|---|---|
| `claude-opus-4-7` | Anthropic Messages | 1,000,000 (1M) | 0.2 | 0 | 5.00 / 25.00 | 2026-07-21 |
| `claude-sonnet-4-6` | Anthropic Messages | 1,000,000 (1M) | 0.2 | 0 | 3.00 / 15.00 | 2026-07-21 |
| `gpt-5` | OpenAI Chat Completions | 400,000 (400K) | 0.2 ⚠️ | 0 ⚠️ | 1.25 / 10.00 | 2026-07-21 |
| `gemini-pro-latest` | Google Gemini API | 1,048,576 (1M) | 0.2 | 0 | 2.00 / 12.00 | 2026-07-22 |

**Max context = the provider-published maximum context window for the model** (prompt + completion combined). ⚠️ **Not captured in the `RunRecord`s** — premium backends serve a fixed provider-side context and report `None` for the loaded-context telemetry (`Backend.context_window`, schema v6; see [`../backends/base.py`](../backends/base.py) L175–181), so these are the *published* ceilings, not a value read back from the runs. The Anthropic figures come from the Models API / model card (1M input, applies to both Opus 4.7 and Sonnet 4.6); GPT-5 is OpenAI's 400K total window (272K input + 128K output); `gemini-pro-latest` is the Gemini Pro tier's 1,048,576-token window. Because `gpt-5` and `gemini-pro-latest` are floating aliases (see the ⚠️ note above), re-verify the ceiling against the provider docs for the exact build if the thesis needs it. The per-run token *budget* the harness actually enforced (`limits.tokens`, e.g. 1M in Trial 3) is a separate cap and is stored in each trial's config — it is not the model's context window.

Pricing snapshot version `2026-07-22` for all trials (rates snapshotted into every
`RunRecord.cost.pricing`).

⚠️ **GPT-5 determinism caveat:** the record stores the *requested* `temperature=0.2`
/ `seed=0`, but GPT-5 is a reasoning model that **rejects both**. The backend omits
them (`OpenAIBackend._send_sampling_params`), so GPT-5 ran at its default
temperature, **non-deterministically**, in every trial. Do not report 0.2/seed=0 as
GPT-5's effective sampling config — cite it in the reproducibility discussion as the
one backend that cannot honor the determinism knobs.

## Reconstructing the exact snapshot (if the model card requires it)

The alias-to-build mapping on the run dates:
- `claude-opus-4-7` / `claude-sonnet-4-6` — version-pinned families; resolve to a
  dated Anthropic snapshot. Anthropic console request logs for 2026-07-22 → 07-27
  are authoritative.
- `gpt-5` — floating alias; OpenAI usage/billing logs for the run dates give the
  resolved build.
- `gemini-pro-latest` — Google's alias for the newest GA Gemini Pro (Gemini 3.x Pro
  tier at the time per `backends/README.md`); resolve from the Google API date.
