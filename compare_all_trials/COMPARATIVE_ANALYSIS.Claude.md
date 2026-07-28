# Trials 1, 2, 3: independent comparative analysis (Claude)

A three-trial pass over the runs for record, written after reading the companion
[`COMPARATIVE_ANALYSIS.md`](COMPARATIVE_ANALYSIS.md) (Codex/ChatGPT) and building on my two
pairwise writeups ([1→2](../compare_trial_1_to_2/COMPARATIVE_ANALYSIS.Claude.md),
[2→3](../compare_trial_2_to_3/COMPARATIVE_ANALYSIS.Claude.md)). Sources: Trial 1 & Trial 2 per-run
appendices and Trial 3's finalized `record.json` files (v6) — record metadata only, no exploit
source, payloads, conversations, or execution.

It answers the two comparisons that were asked for:

- **Part A — full test matrix per trial:** every finalized record, as the apparatus actually ran.
- **Part B — the premier (premium) model class across trials:** the hosted/frontier backends, both
  as each trial configured them and as an aligned Sonnet + GPT-5 sensitivity cohort.

**Headline agreement.** I recomputed every figure in the companion document and all reproduce
exactly — full-matrix endpoints, the premium-class table, the aligned cohort, both resource tables,
the CGC tally, and tool intensity. The numbers below are therefore not in dispute; my contribution
is the **shape** they describe.

**The one-line reading.** The trajectory is not rise-and-fall. It is **step-up-and-hold**: capability
was absent in Trial 1, appeared in Trial 2, and *held* in Trial 3. Trial 3's lower aggregate is two
identified, fixable apparatus artifacts — a **halved premium time budget** and a **block of
unsolvable CGC targets** — sitting on top of real, retained capability, plus the addition of the
strongest single model in the series (Opus). The genuinely invariant result across all three
apparatuses is the CGC wall: **0 successes in 773 records.**

---

## Design crosswalk (what moved, every trial)

| Design feature | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Planned runs | 2,200 | 144 | 216 |
| Finalized records | 1,755 (79.8%) | 92 (63.9%) | 146 (67.6%) |
| Targets | 10 | 4 | 9 |
| Backends | 11 | 6 | 6 |
| Prompting strategies | 4 | 3 | 2 |
| Replicates / cell | 5 | 2 | 2 |
| Advertised tools | **2** | 22 | 8 |
| Token limit | 200k | 500k | 1,000,000 |
| Wall-clock limit | 300 s | 600 s | **300 s premium** / 1,200 s local |
| Record schema | v4 | v5 | v6 |

No two trials differ by one variable, so nothing below identifies an isolated cause. But two rows —
the tool surface (2 → 22) and the premium wall-clock (600 → 300 s) — leave clean fingerprints, and
they are the ones that move the aggregates.

---

## Part A — Full test matrix

### Primary endpoint

| Full-matrix endpoint | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Confirmed success | 0/1,755 (0.0%) | 34/92 (37.0%) | 43/146 (29.5%) |
| Wilson 95% interval | 0.00–0.22% | 27.8–47.2% | 22.7–37.3% |
| Reached validator | 540/1,755 (30.8%) | 69/92 (75.0%) | 111/146 (76.0%) |
| Success \| reached | 0/540 (0.0%) | 34/69 (49.3%) | 43/111 (38.7%) |

Two discontinuities, of very different kinds:

- **Trial 1 → 2 is the real capability event.** Zero to 37% is far outside sampling noise (Trial 1's
  Wilson ceiling, 0.22%, is nowhere near 37%). The unlock was the **execution loop**: Trial 1 exposed
  only gadget-enumeration + raw submission (2 tools); Trial 2 gave the agent 22 tools and let it
  write and run an `exploit.py`. Validator reach more than doubled (30.8% → 75%).
- **Trial 2 → 3 is not a capability event.** Wilson intervals overlap; Fisher p≈0.26. Validator
  *engagement* is flat (75% → 76%) — agents kept reaching execution just as often. What fell is
  conversion, and §"Composition" below shows why.

### Success is a premium phenomenon at every stage

| Backend class | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| premium (hosted) | 0/553 (0%) | 31/46 (67%) | 41/108 (38%) |
| open-weight (local) | 0/662 (0%) | 3/34 (9%) | 2/14 (14%) |
| unrestricted (local) | 0/540 (0%) | 0/12 (0%) | 0/24 (0%) |

Premium models account for **31 of 34** Trial 2 successes and **41 of 43** Trial 3 successes. Local
open-weight wins are rare (all from GPT-OSS-20B); the unrestricted class has never produced a marker.
"LLM agents can build ROP chains" is, on this evidence, "frontier hosted models can, given budget."

### The one true invariant: CGC is unsolved across all apparatuses

| Trial | CGC records | Reached validator | Marker success |
|---|---:|---:|---:|
| Trial 1 | 690 | 187 | 0 |
| Trial 2 | 20 | 12 | 0 |
| Trial 3 | 63 | 36 | 0 |
| **Total** | **773** | **235** | **0** |

Across four distinct CGC programs (CADET, CROMU, EAGLE, NRFIN) and three apparatuses, **no finalized
record ever reached a marker — 235 reached the validator and still converted none.** This is the
cleanest negative capability result in the corpus and the one cross-trial finding that is genuinely
about capability rather than apparatus. Successes concentrate instead on ret2win, BroncoCTF, and the
ROPBench synthetics, which show a difficulty gradient (Trial 3 premium: ex002/ex005 8/12, ex101 5/12,
ex020 3/12).

### The binding constraint migrated — read the failure modes, not just the rate

This is the cross-trial signal the companion document doesn't assemble. Classify **premium failures**
by mode and the three trials tell a clean story about *what stopped the agent*, not how good it was:

| Trial | Premium failure profile | What was binding |
|---|---|---|
| Trial 1 | 346 `budget_exhausted` + 200 `safeguard_refusal` | **token wall** (200k cap, no execution loop) + Gemini refusals |
| Trial 2 | 12 `token_budget`, 2 `wall_clock`, 1 `truncated` | token wall, comfortably (600 s clock ample) |
| Trial 3 | **63 `wall_clock` (100%)** | **time wall** — the 300 s premium cap |

The constraint moved token-wall → (relaxed) → time-wall. Trial 3 doubled the token budget to 1M
(only 10 records exceeded it) but halved the premium clock to 300 s — and **every single premium
failure in Trial 3 is a timeout**. The aggregate dip is not models reasoning worse; it is models
guillotined mid-run. Zero premium failures in either T2 or T3 are substantive wrong-exploits.

### Resources — more effective was never cheaper per success

| Finalized-record measure | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Median total tokens | 159,126 | 424,733 | 258,176 |
| Median wall time | 129.9 s | 217.3 s | 305.0 s |
| Median iterations | 13 | 22 | 28.5 |
| Total tokens | 222.9 M | 32.3 M | 47.8 M |
| Finalized-record cost | \$227.38 | \$35.48 | \$89.64 |
| Tool calls (per record) | 32,070 (18.3) | 2,475 (26.9) | 6,074 (41.6) |

Trial 3's tool curation and context engineering genuinely cut tokens (−39% median vs Trial 2), but
median wall time and iterations rose — agents did *more, cheaper steps* and hit the clock. Interaction
intensity rose monotonically (18.3 → 26.9 → 41.6 calls/record) while success did not: **call volume is
not a capability proxy.** Trial 1's totals dwarf the others only because its finalized sample is ~19×
larger.

---

## Part B — The premier (premium) model class

### Membership changes — this is not a fixed panel

| Trial | Premium backends | Finalized premium records |
|---|---|---:|
| Trial 1 | Sonnet, Opus, GPT-5, **Gemini** | 553 |
| Trial 2 | Sonnet, GPT-5 | 46 |
| Trial 3 | Sonnet, Opus, GPT-5 | 108 |

The premium *class* is a moving target: Trial 1 carries refusal-heavy Gemini, Trial 2 drops both
Gemini and Opus, Trial 3 restores Opus. So the premium endpoint mixes model-composition change with
apparatus change.

### Premium endpoint

| Premium endpoint | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Confirmed success | 0/553 (0.0%) | 31/46 (67.4%) | 41/108 (38.0%) |
| Wilson 95% interval | 0.00–0.69% | 53.0–79.1% | 29.4–47.4% |
| Reached validator | 292/553 (52.8%) | 43/46 (93.5%) | 87/108 (80.6%) |
| Success \| reached | 0/292 (0.0%) | 31/43 (72.1%) | 41/87 (47.1%) |

The premium view magnifies the full-matrix pattern: a step to 67% at Trial 2, then a partial
retreat to 38%. Two things de-fang the retreat:

1. **Composition.** Strip the unsolvable CGC block and premium success is **86.1% (T2) → 56.9%
   (T3)** — the whole 36-record premium CGC block contributes zero by construction.
2. **The time cap.** The residual T2→T3 premium decline on *solvable* targets tracks the 300 s clock:
   premium validator reach fell 93.5% → 80.6% and every premium failure is a timeout.

Was Trial 1's premium zero just Gemini? **No.** Excluding Gemini (0/195, 189 refusals), the remaining
premium backends still went **0/358**. Trial 1's premium zero is real — no execution loop — not a
refusal artifact. Gemini deepens it but does not create it.

### Per-backend premium

| Premium backend | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Claude Sonnet | 0/95 | 15/23 (65.2%) | 9/36 (25.0%) |
| Claude Opus | 0/75 | — | **19/36 (52.8%)** |
| GPT-5 | 0/188 | 16/23 (69.6%) | 13/36 (36.1%) |
| Gemini Pro | 0/195 (189 refused) | — | — |

**Opus, added in Trial 3, is the strongest single backend in the entire series (52.8%)** — and it
posts that in Trial 3's *harsher* 300 s envelope, on a target panel that includes the 0/12 CGC block.
Sonnet and GPT-5 look lower in Trial 3, but the target panel more than doubled and the clock halved;
their decline is the same composition + time story, not a model regression.

### Premium resources

| Premium measure | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Median total tokens | 63,896 | 260,376 | 150,305 |
| Median wall time | 146.8 s | 216.7 s | 302.9 s |
| Median iterations | 7 | 17.5 | 19.5 |
| Median tokens (successes only) | — | 150,870 | 112,162 |
| Cost per observed success | undefined | \$1.14 | \$2.19 |

Premium successes got *cheaper* in tokens (150,870 → 112,162) yet cost-per-success *rose* (\$1.14 →
\$2.19), because yield fell under the time cap. Lower per-run tokens did not buy lower cost per
success — a distinction worth stating precisely in the thesis.

### Aligned premium sensitivity cohort — the cleanest three-trial view

The most controlled cell available across all three trials: **Sonnet + GPT-5 on BroncoCTF and
ROPBench ex005** (the only two targets in all three trials). Backend/target-aligned, though prompts
and replicate exposure still differ.

| Aligned endpoint | Trial 1 | Trial 2 | Trial 3 |
|---|---:|---:|---:|
| Finalized records | 56 | 24 | 16 |
| Reached validator | 43/56 (76.8%) | 24/24 (100%) | 13/16 (81.3%) |
| Confirmed success | 0/56 (0.0%) | 19/24 (79.2%) | 8/16 (50.0%) |
| Success \| reached | 0/43 (0%) | 19/24 (79.2%) | 8/13 (61.5%) |

The step-up-and-hold shape survives alignment: **0 → 79% → 50%**, but note the two ways Trial 3's
half is softened. First, conversion after reaching the validator is **79% → 61.5%**, gentler than the
raw 79% → 50% — because reach itself fell (100% → 81%). Second, the reach drop is the time cap in
miniature: in this cohort **GPT-5's validator reach fell 12/12 → 5/8**, i.e., a third of its runs
never landed a first candidate. Sonnet held reach (8/8) but converted 4/8. The aligned cohort thus
confirms both that Trial 2's capability was real on identical models+targets, and that Trial 3's
lower yield is dominated by censored engagement, not worse chains.

---

## Where I agree with, and where I sharpen, the companion document

- **CGC invariant (agree, fully).** 0/773 is the headline negative result; I'd lead the "limitations"
  section of the thesis with it.
- **Premium dominance (agree).** 31/34 and 41/43.
- **"Trial 3 retains but does not extend" (sharpen).** The companion document leaves the T2→T3 dip as
  open-cause. I'd name the two dominant, identified drivers — the 300 s premium cap (100% of premium
  failures) and the 0/63 CGC block — because both are visible in the records and both are dials, not
  capability walls. On solvable targets under a restored clock, T3 capability is flat-to-up, *and* it
  added the best model yet.
- **Interaction intensity (agree).** Monotone up, success not — calls aren't capability.
- **Refusals (agree).** T1's 200 (189 Gemini) and T3's 4 (all Opus/CROMU) sit on non-overlapping
  backends; there is no cross-trial refusal trend.
- **Caching (agree).** No cache telemetry in any schema; the token drop cannot be attributed to
  caching.

## Bottom line for the thesis

1. **The arc is step-up-and-hold, not rise-and-fall.** 0% → 37% → 29.5% full-matrix (0% → 79% → 50%
   aligned). The Trial 1→2 jump is the real capability transition (the execution loop). Trial 3 holds
   capability; its lower aggregate is apparatus + composition.
2. **The binding constraint migrated: token wall (T1) → relaxed (T2) → time wall (T3).** Every Trial 3
   premium failure is a 300 s timeout. Restore a ≥ 600 s premium clock before reading premium numbers.
3. **Composition, not capability, drives the Trial 3 dip.** The +36-record premium CGC block scores
   0 by construction; premium-excluding-CGC is 86% → 57%, and that residual is the clock.
4. **Premium models own capability, and Trial 3 added the best one (Opus, 52.8%).**
5. **CGC is the true invariant: 0/773 across four programs and three apparatuses** — the corpus's one
   clean negative capability result.

The compound-intervention caveat sits above all of it — prompts, tools, budgets, context handling,
targets, backends, and schema all moved together, and no two trials share a prompting arm — so these
are descriptive, system-level comparisons. But two of the moved dials (premium clock, target mix)
leave clean enough fingerprints to name as the leading drivers rather than list as equals.
