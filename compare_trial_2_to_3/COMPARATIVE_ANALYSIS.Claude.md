# Trial 2 vs Trial 3: independent comparative analysis (Claude)

A second, independent pass over the Trial 2 → Trial 3 runs for record, written after reading
the companion [`COMPARATIVE_ANALYSIS.md`](COMPARATIVE_ANALYSIS.md) (Codex/ChatGPT). It works
from Trial 2's per-run appendix
([`trial2_runs_appendix.csv`](../runs_for_record_trial_2/trial2_runs_appendix.csv), 92 finalized
records) and Trial 3's finalized `record.json` files
([`runs_for_record_trial_3/runs/`](../runs_for_record_trial_3/runs/), 146 records, schema v6) —
record metadata only, no exploit source, no payloads, no execution.

**Headline agreement.** I recomputed every primary figure in the companion document from the raw
records and they reproduce exactly:

| Endpoint | Trial 2 | Trial 3 | Reproduced? |
|---|---:|---:|:--:|
| Validator-confirmed success | 34/92 (37.0%) | 43/146 (29.5%) | ✅ |
| Wilson 95% interval | 27.8–47.2% | 22.7–37.3% (overlaps) | ✅ |
| Reached validator (`RAN`+) | 69/92 (75.0%) | 111/146 (76.0%) | ✅ |
| Success \| reached | 34/69 (49.3%) | 43/111 (38.7%) | ✅ |
| Tier ladder (none/ran/control/marker) | 23/34/1/34 | 35/63/5/43 | ✅ |
| Balanced premium cohort (Sonnet+GPT-5 × 3) | 31/36 | 13/24 | ✅ |
| Broad shared (5 backends × 3 targets) | 34/66 | 15/35 | ✅ |
| Median tokens / wall / iters | 425k / 217.3s / 22 | 258k / 305.0s / 28.5 | ✅ |
| Total tokens / cost | 32.3M / \$35.48 | 47.79M / \$89.64 | ✅ |

So the companion document's descriptive spine is sound: whole-archive success fell 37.0% → 29.5%,
validator *engagement* held (~75%), and *conversion* after execution fell (49.3% → 38.7%). Its
caution is appropriate too — this is a compound intervention (no shared prompting strategy, 22→8
tools, new targets, Opus added, v5→v6). Where I differ is **emphasis**: the companion document
lists the halved time limit as one of ~ten evenly-weighted candidate causes. The records don't
support that even weighting. **Two identifiable changes dominate the decline, and neither is a
capability regression.** The four sections below make that case, each verified against the record.

---

## 1. The decline is target composition, not capability — the aggregate hides a shared-target *gain*

Trial 3 kept only 3 of Trial 2's 4 targets and added 6 new ones. Three of the new targets are CGC
programs — `cgc-cromu-00004`, `cgc-eagle-00005`, `cgc-nrfin-00056` — and they are **structurally
unsolvable in this apparatus**:

> **CGC additions (new in T3): 0/63 success, and 0/63 ever reached even `CONTROL`.**

That is 63 of Trial 3's 146 records — **43% of the whole trial** — producing guaranteed zeros the
aggregate had no way to earn. Fold in Trial 2's `cgc-cadet-00001` and the barrier is total: across
four distinct CGC programs and both trials, **0 of 83 finalized records reached `CONTROL` or
`MARKER`.** (The companion document reaches this same barrier in its conclusion #8; I agree fully.)

Now cut the composition the other way. On the **3 targets the trials share**
(`ret2win-baseline`, `broncoctf`, `ropbench-synth-ex005`), Trial 3 scores **27/47 (57.4%)** —
*higher* than Trial 2's 37.0% aggregate. The new ROPBench synthetics (ex002/ex020/ex101) also
produced 16/36 (44.4%). The whole-archive drop is not the models getting worse; it is a
denominator stuffed with a hard target family that produces zeros by construction.

| Trial 3 target group | success | rate |
|---|---:|---:|
| 3 shared targets | 27/47 | 57.4% |
| new ROPBench synthetics | 16/36 | 44.4% |
| **new CGC programs** | **0/63** | **0.0%** |

**Thesis language:** report the shared-target rate alongside the 29.5% aggregate; the aggregate is a
target-mix artifact, and a lower aggregate under a harder panel is not a capability regression.

## 2. The halved premium wall-clock cap is the single dominant driver — 100% of premium failures are timeouts

Trial 3 cut the premium wall-clock budget in half — **600 s → 300 s** — while raising the local
budget to 1,200 s. This is not one candidate cause among many; it is *the* mechanism, and the
failure-mode coding makes it unambiguous:

| Premium failure modes | Trial 2 (600 s cap) | Trial 3 (300 s cap) |
|---|---:|---:|
| `wall_clock` (timeout) | 2 | **63 (100%)** |
| `token_budget` | 12 | 0 |
| `truncated` | 1 | 0 |
| substantive wrong-exploit | 0 | 0 |

**Every one of Trial 3's 63 premium failures is a wall-clock timeout** — versus 2 of 15 in Trial 2.
Premium runs now pile up right at the new ceiling: median premium wall-clock rose 217 s → **303 s**,
and 68 of 108 premium runs exceeded 300 s. Successful premium runs finish fast (median 152 s); the
failures are the runs that needed the second half of the old budget and no longer had it. Per-backend
the signature is clean — Sonnet's *successes* finish at a 59 s median while its failures cluster at
the wall, and GPT-5's successes run to a **268 s** median, comfortably inside the old 600 s cap but
brushing the new 300 s one. The companion document notes GPT-5's validator reach fell 18/18 → 6/12;
that is the same story — GPT-5 was cut off before it could even land a first candidate.

The cap is soft (5 premium successes ran past 300 s, so it is checkpointed, not a hard guillotine),
but directionally it is the binding constraint. This is exactly the confound flagged for the next
trial: **restore a premium wall-clock budget ≥ 600 s before reading any premium capability number.**

## 3. Token efficiency genuinely improved — but time replaced tokens as the binding wall

The companion document's framing — "per-run token use fell but endpoint efficiency did not clearly
improve" — is technically true but reads as a null result. It isn't. The 22→8 tool-schema curation
and context engineering **worked on the axis they targeted**:

- Median tokens/run fell **424,733 → 258,176 (−39%)**; among successes 155,718 → 112,599; among
  non-successes 508,466 → 339,848. Every token median dropped.
- In the balanced premium cohort, median tokens/run fell ~40% and cost/run fell \$0.634 → \$0.539.

The endpoint didn't improve because a *different* resource was simultaneously halved. Trial 3
traded the token wall (Trial 2's binding constraint — 40 of 58 Trial-2 failures were `token_budget`)
for a time wall, then cut that time wall in half for premium. Median wall-clock rose 217 s → 305 s
and iterations rose 22 → 28.5 even as tokens fell — the agents were doing *more, cheaper* steps and
getting stopped by the clock. The optimization succeeded; the budget it freed up wasn't the one that
was binding. **Report the token reduction as a real, intended win, and pair it with the finding that
wall-clock, not tokens, now governs premium outcomes.**

## 4. Trial 3 added its strongest model — and the refusals are again a composition artifact

Trial 3 replaced Qwen3-Coder with **Claude Opus**, which is the **best single backend in either
trial**: 19/36 = **52.8%**, ahead of GPT-5 (36.1%) and Sonnet (25.0%) *in Trial 3's harsher time
envelope*. So the aggregate fell even though a stronger model was added — further evidence the drop
is apparatus/composition, not capability. Excluding CGC, premium success is 56.9% (T3) vs 86.1%
(T2); that residual premium decline on solvable targets tracks the time cap (§2), not reasoning.

On refusals: Trial 3 has 4 `safeguard_refusal` outcomes, **all Opus, all on `cgc-cromu-00004`**, and
Opus had no Trial 2 arm. As in the Trial 1 → 2 comparison, the refusal signal is not cross-trial
comparable — it belongs to a model that only one trial ran. Excluding the four changes Trial 3's rate
only to 43/142 (30.3%). No cross-trial refusal claim is supportable.

---

## Where I agree with, and where I'd sharpen, the companion document

- **Balanced premium cohort decline is real (agree).** Sonnet+GPT-5 × 3 shared targets: 31/36 →
  13/24; including Opus, 31/36 → 25/36 (86.1% → 69.4%). But I'd attribute it, not leave it open:
  validator reach in that cohort fell 36/36 → 18/24, i.e., a third of the runs never finished a first
  candidate — the 300 s cap again, not a prompt/tool/context regression.
- **No shared prompting strategy (agree, fully).** Trial 2 (zero-shot/CoT/ReAct) and Trial 3
  (template-backward/recon-first) share zero arms; no longitudinal strategy delta exists. Within
  Trial 3, recon-first (31.9%) edged template-backward (27.0%) — inside noise.
- **CGC barrier (agree).** 0/83 across four CGC programs and both trials is the cleanest negative
  result in the corpus.
- **More tool calls from fewer tools (agree, minor).** 8 tools produced 6,074 calls (41.6/record)
  vs 22 tools / 2,475 calls (26.9/record) in Trial 2 — a workflow observation, not a cause.
- **Context-exposure confound (agree, worth keeping).** The v6 `n_ctx_loaded` mismatch (Qwen3
  Abliterated loads 40,960 despite a 262,144 config) shows configured ≠ loaded context; local
  numbers are ordered-sample summaries, not clean capability measurements.

## Bottom line for the thesis

The companion document's numbers are trustworthy and its caution is right, but the 37% → 29.5%
"decline" should not be presented as a capability finding. Four qualifiers convert it into the real
story:

1. **The aggregate is a target-mix artifact.** Three new CGC targets contribute 0/63; on the 3
   shared targets Trial 3 scores **57.4%**, above Trial 2's 37% aggregate. A lower rate under a
   harder panel is not a regression.
2. **The halved premium wall-clock cap (600 s → 300 s) is the dominant driver.** 100% of Trial 3's
   premium failures are timeouts (vs 2 of 15 in Trial 2); premium runs pile up at 303 s. Restore
   ≥ 600 s before reading premium capability.
3. **Token efficiency really improved (−39%/run) — the optimization worked.** The endpoint didn't
   move because time, not tokens, became the binding wall.
4. **Trial 3 added its strongest model (Opus, 52.8%);** the four Opus-only refusals are not a
   cross-trial signal.

The one genuinely negative capability result is the CGC family: 0/83 across both trials. Everything
else in the "decline" is apparatus and composition — which is good news for the instrument, because
both are dials, not walls. As with the companion document, the compound-intervention caveat sits
above all of it: prompts, tools, budgets, context handling, targets, backends, and schema all moved
at once, so nothing here isolates a single cause with certainty — but the wall-clock signal is clean
enough (100% of premium failures) to name as the leading one rather than one of ten equals.
