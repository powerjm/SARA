# Trial 1 vs Trial 2: independent comparative analysis (Claude)

This is a second, independent pass over the same two runs for record, written after
reading the companion [`COMPARATIVE_ANALYSIS.md`](COMPARATIVE_ANALYSIS.md) (Codex/ChatGPT).
It works from the archived per-run appendices
([`trial1_runs_appendix.csv`](../runs_for_record_trial_1/trial1_runs_appendix.csv),
1,755 finalized records; [`trial2_runs_appendix.csv`](../runs_for_record_trial_2/trial2_runs_appendix.csv),
92 finalized records) — record metadata only, no exploit source, no payloads, no execution.

**Headline agreement.** I recomputed every primary figure in the companion document
from the raw appendices and they reproduce exactly:

| Endpoint | Trial 1 | Trial 2 | Reproduced? |
|---|---:|---:|:--:|
| Validator-confirmed success | 0/1,755 (0.0%) | 34/92 (37.0%) | ✅ |
| Record reached validator | 540/1,755 (30.8%) | 69/92 (75.0%) | ✅ |
| Success \| reached validator | 0/540 (0.0%) | 34/69 (49.3%) | ✅ |
| Common-coverage subset (n) | 118 | 52 | ✅ |
| Common-coverage reached / success | 57 / 0 | 46 / 20 | ✅ |
| Shared-backend T1 reach (Sonnet / GPT-5 / GPT-OSS) | 22/30 · 26/44 · 9/44 | — | ✅ |
| Median tokens / wall / iters | 159k / 129.9s / 13 | 425k / 217.3s / 22 | ✅ |

So the companion document's descriptive spine is sound: **Trial 2 is the first trial to
demonstrate validator-confirmed, end-to-end capability, and the sharpest jump is in
conversion *after* a run reaches the validator (0/540 → 34/69).** I do not dispute any of
that. This document adds four things its framing understates or omits, each of which
changes how the numbers should be read in the thesis.

---

## 1. A trivial new target supplies 41% of Trial 2's successes

Trial 2 introduced a target that did not exist in Trial 1: **`ret2win-baseline`**, a
textbook single-gadget "ret2win" — the "hello world" of ROP. It is the single largest
slice of Trial 2 (36 of 92 records) and it alone accounts for **14 of the 34 successes**.

| Trial 2 target | n | reached | success | rate |
|---|---:|---:|---:|---:|
| ret2win-baseline *(new, trivial)* | 36 | 23 | 14 | 38.9% |
| ropbench-synth-ex005 | 18 | 18 | 12 | 66.7% |
| broncoctf2026-proper-pwning | 18 | 16 | 8 | 44.4% |
| cgc-cadet-00001 | 20 | 12 | 0 | 0.0% |

The companion document's target section discusses only the three *shared* targets and never
names `ret2win-baseline`, so a reader is left to assume all 34 successes came from
Trial-1-comparable targets. They did not.

This is **not** fatal to the headline — I checked. Dropping `ret2win-baseline` for an
apples-to-apples comparison against Trial 1's target panel still leaves **20/56 (35.7%)**
overall and **19/34 (55.9%)** among premium models. The discontinuity from Trial 1's zero
survives. But the aggregate "37.0%" is partly a composition artifact of adding an easy
target, and the thesis should quote the ex-`ret2win` figure alongside it rather than the
raw aggregate alone.

## 2. Trial 2's zero refusals are a composition artifact, not a solved problem

Every one of Trial 1's 200 `safeguard_refusal` outcomes came from exactly two backends:
**gemini-pro-latest (189)** and **claude-opus-4-7 (11)**. Trial 2's panel contains
*neither* model. Trial 2 therefore records zero refusals — but by construction, not because
refusal behavior improved. The two refusal-prone models were simply removed from the matrix.

The companion document lists "model composition" as a generic threat to validity; I'd state
it concretely: the entire refusal signal disappears between trials **because the refusers
were dropped**, so no cross-trial statement about safety/refusal trends is supportable. Any
refusal discussion in the thesis has to be made *within* Trial 1.

## 3. 100% of Trial 2 failures are resource-wall hits — the ceiling is budget, not capability

This is the finding I think matters most and the companion document misses. Classifying the
58 Trial 2 failures by mode:

| Trial 2 failure mode | count |
|---|---:|
| token_budget (ran out of the 500k token budget) | 40 |
| wall_clock (hit the 600s wall) | 12 |
| truncated (context truncation) | 6 |
| **genuine wrong/failed exploit** | **0** |

**Not one Trial 2 failure is a substantive "the agent tried and produced a wrong exploit"
outcome.** Every failure is the harness cutting the run off at a resource boundary. Combined
with the resource medians (Trial 2 spent 2.7× the tokens and 1.7× the wall-clock of Trial 1),
this reframes the companion document's conclusion #7 ("the gain came under a larger resource
envelope"). The stronger, more precise statement is: **Trial 2's success rate is
budget-limited, not capability-limited** — the models were still mid-attempt when the walls
stopped them, so raising the budget is the obvious lever, and the observed 37% is a *floor*
under the current envelope, not a capability ceiling. (This is exactly what Trial 3 went on
to confirm: raising the token budget to 1M lifted premium success and exposed a wall-clock
cap as the next binding constraint.)

Trial 1's failures were also dominated by a resource wall (1,079/1,555 `budget_exhausted`),
so the through-line across both trials is the same: **outcomes are governed by where the
resource walls sit far more than by model reasoning quality.** The walls moved; the story
didn't.

## 4. The success story is almost entirely a premium-model story

Stratifying Trial 2 by backend category makes the aggregate much less impressive as a
statement about "LLM agents" in general:

| Trial 2 category | n | reached | success | rate |
|---|---:|---:|---:|---:|
| premium (Sonnet, GPT-5) | 46 | 43 | 31 | **67.4%** |
| open_weight (GPT-OSS-20B, qwen3-coder) | 34 | 23 | 3 | 8.8% |
| unrestricted (whiterabbitneo, huihui-qwen) | 12 | 3 | 0 | 0.0% |

**Sonnet + GPT-5 alone account for 31 of the 34 successes.** The three non-premium
categories combined produced 3 successes in 46 records, all from GPT-OSS-20B. The companion
document's conclusion #4 notes success is "concentrated by model," but the premium/open/
unrestricted split is a cleaner cut than the per-model view and connects to the design's own
category taxonomy: on this evidence the capability exists at the premium tier and is
essentially absent below it. GPT-OSS-20B is the useful separator the companion document
already flags — high engagement (reached the validator 21/24 times across the full matrix),
low capability (3 successes) — and I agree that engagement must never be read as capability.

---

## Where I'd temper the companion document's framing

- **"ReAct led" (its shared-strategy table).** On the full Trial 2 matrix the strategy
  spread is 34–41% (react 41.4%, cot 35.5%, zero_shot 34.4%) across ~30 records each — well
  inside noise, and entangled with which backend/target each cell drew. The companion
  document does hedge this in prose; I'd go further and say the strategy factor is
  **not separable** from model and target at this n, full stop.
- **Progress-ladder comparison.** Agreed that v4→v5 schema change makes the middle rungs
  non-comparable. The only cross-trial-safe rungs are "reached validator" and "confirmed
  success," which is what I've used throughout. Trial 2's own tier field
  (`max_tier_reached`: 34 `marker`, 34 `ran`, 23 `none`, 1 `control`) is a clean *within-
  trial* signal but shouldn't be laddered against Trial 1.

## Bottom line for the thesis

Trial 2 is a real, verifiable capability result and the companion document's numbers are
trustworthy. But four qualifiers belong next to the 37% headline:

1. Quote **35.7% ex-`ret2win-baseline`** alongside the 37% aggregate — the trivial new
   target carries ~41% of the raw successes.
2. Trial 2's **zero refusals are because the refusing models were removed**, not because
   refusal was solved — no cross-trial refusal claim is supportable.
3. **Every Trial 2 failure is a resource-wall hit (0 substantive failures)** — the result is
   budget-limited, so 37% is a floor under the current envelope, not a capability ceiling.
4. The capability is a **premium-tier phenomenon** (67% premium vs 9% open-weight vs 0%
   unrestricted); Sonnet + GPT-5 own 31 of 34 successes.

None of these overturn the central finding — end-to-end ROP capability that was absent in
Trial 1 is present in Trial 2, concentrated after the validator stage — but together they
convert an eye-catching aggregate into a defensible, stratified claim, which is what backup
material for a thesis needs. As with the companion document, the compound-intervention
caveat stands above all of it: tools, budgets, targets, models, replication, and scoring
schema all changed at once, so nothing here isolates a single cause.
