# Trial 2 versus Trial 3: comparative analysis

## Scope and evidentiary boundary

This document independently compares the second and third formal “runs for
record” trials using experiment configuration, launcher logs, and finalized
`record.json` metadata. It does **not** inspect submitted exploit source,
payloads, target binaries, conversations, or execution traces, and it does not
execute any submission. The analysis is intended as descriptive backup material
for an academic thesis.

Trial 3 is not a single-factor replication of Trial 2. Its target panel,
backend panel, prompting methods, exposed tools, resource limits, context
handling, and record schema all changed. Cross-trial differences therefore
describe realized performance under two compound experimental apparatuses; they
do not identify the causal effect of prompting, tool curation, caching, context
engineering, or any model change in isolation.

The strongest available descriptive contrast is a balanced cohort containing
the two premium backends and three targets fully represented in both trials:
Claude Sonnet and GPT-5 on ret2win, BroncoCTF, and ROPBench ex005. Even this
cohort is balanced only on backend and target. Trial 2 contributes six attempts
per backend-target pair (three strategies × two replicates), whereas Trial 3
contributes four (two different strategies × two replicates), and the nominal
premium wall-clock limit changed from 600 to 300 seconds.

## Experimental-design crosswalk

| Design feature | Trial 2 | Trial 3 | Comparative implication |
|---|---:|---:|---|
| Planned runs | 144 | 216 | Trial 3 planned a broader target matrix |
| Finalized records | 92 (63.9%) | 146 (67.6%) | Both archives have substantial, structured attrition |
| Initiated but unfinalized | 4 | 3 | These are separate from finalized endpoints |
| Never started | 48 | 67 | Planned matrices were not uniformly realized |
| Targets | 4 | 9 | Only three targets are shared |
| Backends | 6 | 6 | Five are shared; Opus replaces Qwen3 Coder |
| Prompting strategies | 3 | 2 | **No strategy is shared across trials** |
| Replicates per planned cell | 2 | 2 | Nominal replication is unchanged |
| Exposed tool set | 22 tools | 8 tools | Tool identities and workflow semantics changed |
| Token limit | 500,000 | 1,000,000 | Trial 3 doubled the nominal token envelope |
| Wall-clock limit | 600 s for all | 300 s premium; 1,200 s local | Exposure changed in opposite directions by backend class |
| Maximum iterations | 100 | 100 | Nominal turn ceiling is unchanged |
| Record schema | v5 | v6 | Common endpoints remain comparable; new v6 fields are one-sided |

The planned products are 4 targets × 6 backends × 3 strategies × 2
replicates = 144 runs in Trial 2 and 9 × 6 × 2 × 2 = 216 in Trial 3. The
aggregate configuration files are consistent with these products, although the
launcher logs show that execution was split across premium and local batches.
The exact invoked split files are not retained, so the record and logs, rather
than a claim of byte-identical configuration provenance, are the evidentiary
basis for realized coverage.

## Primary endpoint

![Primary endpoint forest plot](diagrams/01_primary_endpoint_forest.png)

| Endpoint | Trial 2 | Trial 3 | Observed change |
|---|---:|---:|---:|
| Validator-confirmed success | 34/92 (37.0%) | 43/146 (29.5%) | −7.5 percentage points |
| Descriptive Wilson 95% interval | 27.80–47.16% | 22.66–37.30% | Intervals overlap |
| `RAN` or above / validator result | 69/92 (75.0%) | 111/146 (76.0%) | +1.0 point |
| `CONTROL` or above | 35/92 (38.0%) | 48/146 (32.9%) | −5.2 points |
| Success conditional on `RAN`+ | 34/69 (49.3%) | 43/111 (38.7%) | −10.5 points |

The whole-archive success endpoint declined from 37.0% to 29.5%. A descriptive
run-level Fisher exact test gives approximately \(p=0.256\); the corresponding
conditional-conversion comparison gives approximately \(p=0.215\). These
values do not establish equivalence, and they are not design-adjusted:
replicates are clustered within backend-target-strategy cells, finalized
records are not a random sample of the planned matrix, and the trial apparatus
changed substantially.

The progress decomposition is more informative than the aggregate endpoint.
Validator engagement remained almost identical, while conversion from a
recorded validator result to marker success fell by 10.5 points. Thus Trial 3
did not fail primarily because agents stopped attempting candidates more often;
the lower realized yield appeared after or around the candidate-execution
stage.

## Progress ladders and outcome coding

![Side-by-side progress ladders](diagrams/02_progress_ladders.png)

| Maximum tier | Trial 2 | Trial 3 |
|---|---:|---:|
| `NONE` | 23 (25.0%) | 35 (24.0%) |
| `RAN` | 34 (37.0%) | 63 (43.2%) |
| `CONTROL` | 1 (1.1%) | 5 (3.4%) |
| `MARKER` | 34 (37.0%) | 43 (29.5%) |

Schema v6 adds score, context, and bonus fields, but the four common tier labels
and marker endpoint support the ladder comparison. Trial 3’s four
`safeguard_refusal` outcomes are not a fifth progress tier: two are `NONE` and
two are `RAN`. All four are Claude Opus × CGC CROMU records, and their retained
outcome coding is potentially ambiguous. The intention-to-treat-style primary
summary retains them. Excluding them as a sensitivity analysis changes Trial
3’s overall rate only to 43/142 (30.3%) and premium rate to 41/104 (39.4%).
Because Opus had no Trial 2 arm and the classification is potentially
instrumentation-related, these records do not support a claim of a
cross-trial refusal increase.

## Comparability and shared coverage

The trials share:

- three targets: ret2win baseline, BroncoCTF 2026 Proper Pwning, and ROPBench
  ex005;
- five backends: Claude Sonnet, GPT-5, GPT-OSS 20B, Qwen3 Abliterated, and
  WhiteRabbitNeo 7B; and
- **zero prompting strategies**.

Collapsing across the five shared backends and three shared targets produces
34/66 successes (51.5%) in Trial 2 and 15/35 (42.9%) in Trial 3. This broad
restriction is still composition-biased because the local backend-target
blocks are incomplete and differ between trials. It should not be treated as a
matched estimator.

The balanced premium cohort is more defensible:

| Balanced Sonnet + GPT-5 × three-target cohort | Trial 2 | Trial 3 |
|---|---:|---:|
| Finalized records | 36 | 24 |
| Reached validator | 36/36 (100.0%) | 18/24 (75.0%) |
| Confirmed success | 31/36 (86.1%) | 13/24 (54.2%) |
| Descriptive Wilson 95% interval | 71.34–93.92% | 35.07–72.11% |
| Success after validator | 31/36 (86.1%) | 13/18 (72.2%) |

The observed success difference is −31.9 percentage points. A run-level Fisher
test is approximately \(p=0.0084\), but this must remain descriptive: the
attempts are clustered and differ in prompt, exposed tools, context management,
and nominal time. The result supports “lower realized yield under the Trial 3
apparatus,” not “the Trial 3 prompt/tool/context change caused harm.”

## Shared backends

![Shared-backend dumbbell plot](diagrams/03_shared_backend_dumbbell.png)

The figure shows all five shared backends on the three shared targets, retaining
the uneven local coverage rather than silently imputing missing runs.

| Backend | Trial 2 success | Trial 3 success | Trial 2 validator | Trial 3 validator |
|---|---:|---:|---:|---:|
| Claude Sonnet | 15/18 (83.3%) | 8/12 (66.7%) | 18/18 | 12/12 |
| GPT-5 | 16/18 (88.9%) | 5/12 (41.7%) | 18/18 | 6/12 |
| GPT-OSS 20B | 3/18 (16.7%) | 2/3 (66.7%) | 16/18 | 3/3 |
| Qwen3 Abliterated | 0/6 | 0/4 | 3/6 | 4/4 |
| WhiteRabbitNeo 7B | 0/6 | 0/4 | 0/6 | 2/4 |

Only the Sonnet and GPT-5 rows are balanced with respect to the shared target
panel. Sonnet declined by 16.7 points and GPT-5 by 47.2 points. GPT-5’s
validator reach also changed from 18/18 to 6/12. This pattern is consistent with
a meaningful exposure difference—the nominal premium limit halved, and Trial 3
GPT-5 successes had a 268-second median—but it cannot establish that more time
would have yielded success.

The local rows are too small and compositionally incomplete for longitudinal
model rankings. They do show a narrower point: Qwen3 Abliterated and
WhiteRabbitNeo engaged the validator more often in their realized Trial 3
baseline blocks, but neither produced a marker success.

## Shared targets

![Shared-target conversion plot](diagrams/04_shared_target_conversion.png)

Within the balanced Sonnet/GPT-5 cohort:

| Target | Trial 2 success | Trial 3 success | Trial 2 validator | Trial 3 validator |
|---|---:|---:|---:|---:|
| BroncoCTF | 8/12 (66.7%) | 4/8 (50.0%) | 12/12 | 5/8 |
| ret2win baseline | 12/12 (100.0%) | 5/8 (62.5%) | 12/12 | 5/8 |
| ROPBench ex005 | 11/12 (91.7%) | 4/8 (50.0%) | 12/12 | 8/8 |

The decline is not confined to one target, although denominators are small.
Trial 3 also expands the target panel: its additional ROPBench synthetics
produced successes, while the CGC targets did not. Across Trial 2 CADET and
Trial 3 CROMU, EAGLE, and NRFIN, 0/83 finalized records reached `CONTROL` or
`MARKER` (0/79 if the ambiguous Opus refusals are excluded). This is consistent
with a recurring observed barrier across four distinct CGC programs, but it is
not a same-target replication and does not identify the mechanism.

## Prompting strategies: no longitudinal arm

![Backend by trial-specific strategy heatmap](diagrams/05_backend_strategy_delta_heatmap.png)

Trial 2 used zero-shot, chain of thought, and ReAct; Trial 3 used template
backward and recon first. Since no strategy label or prompt treatment is shared,
a cross-trial “strategy delta” would be invalid. The figure therefore places
separate within-trial columns on the same shared-target display and explicitly
does not encode them as matched treatments.

| Within-trial strategy | Success / finalized |
|---|---:|
| Trial 2 zero-shot | 11/32 (34.4%) |
| Trial 2 chain of thought | 11/31 (35.5%) |
| Trial 2 ReAct | 12/29 (41.4%) |
| Trial 3 template backward | 20/74 (27.0%) |
| Trial 3 recon first | 23/72 (31.9%) |

These small within-trial differences do not establish a stable generic prompt
ranking. Backend, target, exposure, and missingness remain entangled with the
observed rates.

## Tool-mediated workflow

![Tool-use composition](diagrams/06_tool_use_composition.png)

Trial 2 offered 22 tools and recorded 2,475 calls (26.9 per finalized record).
Trial 3 offered eight tools and recorded 6,074 calls (41.6 per record). Trial 2
calls were spread across enumeration, execution, search, disassembly, gadget
search, decompilation, debugging, and submission. Trial 3 was concentrated in
gadget search (2,031; 33.4%), command/script execution (1,747; 28.8%), Radare2
disassembly (1,069 after merging five typo aliases; 17.6%), Radare2
reconnaissance (665; 10.9%), and GDB disassembly (459; 7.6%).

The smaller exposed tool set did not yield fewer recorded interactions. Typical
successful records had nearly unchanged call counts (median 17.5 to 17), while
ordinary failures rose from a median of 32 to 51 calls. Two Trial 3
WhiteRabbitNeo outliers account for 603 calls, so the mean intensity should not
be read without that qualification. These are workflow observations, not
evidence that any tool caused or prevented success.

## Validator conversion

![Conditional validator conversion](diagrams/07_conditional_conversion.png)

Across all finalized records, Trial 3 maintained validator reach but converted a
smaller fraction of reached runs into marker success. The same direction
appears in the broad shared-factor subset (61.8% to 55.6%) and balanced premium
cohort (86.1% to 72.2%). The balanced cohort also shows that part of its larger
endpoint decline arose before validator engagement: Trial 3 reached a validator
in only 18/24 records, versus 36/36 in Trial 2.

## Resource use and observed efficiency

![Resource-use empirical distributions](diagrams/08_resource_ecdfs.png)

| Resource metric | Trial 2 | Trial 3 |
|---|---:|---:|
| Median total tokens, all records | 424,733 | 258,176 |
| Median total tokens, successes | 155,718 | 112,599 |
| Median total tokens, nonsuccesses | 508,466 | 339,848 |
| Median wall time, all records | 217.3 s | 305.0 s |
| Median wall time, successes | 153.8 s | 151.8 s |
| Median wall time, nonsuccesses | 242.8 s | 325.3 s |
| Median iterations, all records | 22 | 28.5 |
| Total recorded tokens | 32.30 million | 47.79 million |
| Total recorded cost | $35.48 | $89.64 |

Per-record token medians fell, including among both successes and
nonsuccesses, while wall time and iterations rose for the latter. Aggregate
tokens and cost increased because Trial 3 finalized more records and introduced
Opus. In the balanced premium cohort, median tokens fell 40.1% per run and
recorded cost fell from $0.634 to $0.539 per run, but cost per observed success
rose from $0.737 to $0.995 because yield fell. This distinction is useful:
lower resource use per attempt did not translate into better endpoint
efficiency under the changed apparatus.

The records contain no cache-read, cache-write, or cache-hit telemetry.
Consequently, the token reduction cannot be causally attributed to caching.
Plausible contributors include the 22-to-8 tool-schema reduction, compaction,
new prompts, model and target composition, outcome mix, and earlier premium
wall censoring. A caching-effect estimate would require provider usage telemetry
or a cached-versus-uncached control.

Trial 3’s v6 `n_ctx_loaded` field adds useful but one-sided context telemetry.
All finalized GPT-OSS records report 131,072 tokens and all WhiteRabbitNeo
records 32,768; Qwen3 Abliterated reports 40,960 in all 12 records despite a
262,144 per-backend value in the aggregate configuration. This runtime/config
mismatch is a context-exposure confound and illustrates why configured capacity
should not be treated as observed loaded context.

Nominal limits were also soft or checkpointed rather than hard exposure bounds.
Trial 2 has 42 finalized records above 500,000 tokens and 14 above 600 seconds.
Trial 3 has 10 records above one million tokens, 68/108 premium records above
300 seconds, and 17 local records above 1,200 seconds; five premium successes
also exceeded 300 seconds. Configuration thresholds therefore should not be
treated as exact censoring times.

## Coverage and ordered attrition

![Backend-target matrix coverage](diagrams/09_matrix_coverage_mosaic.png)

Trial 2 finalized 92/144 planned records, with four additional initiated but
unfinalized attempts and 48 never started. Trial 3 finalized 146/216, with three
initiated but unfinalized attempts and 67 never started. In both trials,
missingness follows execution order:

- Trial 2 premium coverage is 46/48; local coverage is 46/96. GPT-OSS is
  complete, Qwen3 Coder stops partway through CADET, and the remaining two local
  backends reached only ret2win.
- Trial 3 premium coverage is complete at 108/108; local coverage is 38/108.
  Local runs cover ret2win, CROMU, and EAGLE, with only GPT-OSS reaching NRFIN;
  no local backend reached Bronco or any ROPBench synthetic.

Aggregate local model or target rates are therefore ordered-sample summaries,
not estimates from exchangeable missingness. Trial 3 contains 72 complete
factor cells, two singleton cells, and 34 missing cells; Trial 2 contains 45
complete, two singleton, and 25 missing cells. The mosaic makes this structure
visible and is essential context for any model-level aggregate.

## BroncoCTF progression

![BroncoCTF milestone progression](diagrams/10_bronco_milestones.png)

Among finalized Bronco records, retained validator output indicates Gate 1 or
later in 11/18 Trial 2 records and 8/12 Trial 3 records, Gate 3 or later in
10/18 and 8/12, and marker success in 8/18 and 8/12. In Trial 3, all eight
records with retained gate text are marker records and the four nonmarkers
retain none. The display is therefore both a task-progress measure and a
record-retention measure; it should not be interpreted as complete latent
within-run trajectory evidence.

## Conclusions suitable for thesis backup material

1. **Whole-archive realized success was lower in Trial 3.** The marker endpoint
   declined from 37.0% to 29.5%, while the run-level descriptive intervals
   overlap and the design does not support a causal interpretation.
2. **Validator engagement was stable, but conversion was lower.** `RAN`+
   remained approximately 75%, while marker success conditional on `RAN`+
   declined from 49.3% to 38.7%.
3. **The balanced premium/shared-target cohort shows a larger decline.**
   Sonnet and GPT-5 moved from 31/36 to 13/24 successes. This is strong
   descriptive evidence of lower yield under the Trial 3 apparatus, not an
   isolated prompt, tool, context, caching, or time-limit effect.
4. **GPT-5 accounts for much of that cohort contrast.** Its success moved from
   16/18 to 5/12 and validator engagement from 18/18 to 6/12; simultaneous
   apparatus changes preclude a single-cause explanation.
5. **There is no valid longitudinal prompting-strategy comparison.** The trials
   share no strategy arm.
6. **A narrower tool surface produced more recorded tool calls.** Trial 3
   failures in particular show longer interaction sequences, without a
   corresponding endpoint gain.
7. **Per-run token use fell, but endpoint efficiency did not clearly improve.**
   Balanced-cohort cost per run fell while cost per observed success rose.
   Caching effects are not identifiable from the retained telemetry.
8. **The CGC family remained an observed barrier.** Across four distinct CGC
   targets and both trials, no finalized record reached `CONTROL` or `MARKER`.
9. **Coverage is structured and must accompany aggregate rates.** Ordered local
   attrition makes full-backend and full-target comparisons compositionally
   biased.
10. **Trial 3 increases breadth and instrumentation, not comparability.** New
    targets, Opus, v6 fields, and context telemetry add useful evidence but do
    not turn Trial 3 into a controlled replication of Trial 2.

## Threats to validity

- **Compound intervention:** prompts, tools, limits, context handling, targets,
  backends, and schema changed together.
- **No shared prompt treatment:** backend-target restriction cannot align
  prompting exposure.
- **Structured missingness:** local execution stopped in target order in both
  trials.
- **Soft limits:** recorded exposure often exceeds nominal limits and may do so
  differently by backend.
- **Clustered replicates:** simple intervals and exact tests treat runs as
  independent and therefore understate design complexity.
- **Small subgroup denominators:** many comparative cells contain only four to
  eighteen observations.
- **Schema asymmetry:** v6 adds score and context fields that have no v5
  counterpart.
- **Refusal ambiguity:** four Trial 3 Opus outcomes may reflect behavior,
  orchestration, or classification and have no Trial 2 Opus comparator.
- **No cache telemetry:** causal claims about caching are unsupported.
- **Milestone retention:** Bronco gate counts are based only on retained
  final-record stdout excerpts.

## Reproducibility and figure index

The companion scripts
[`compute_comparison_stats.py`](compute_comparison_stats.py) and
[`generate_comparison_diagrams.py`](generate_comparison_diagrams.py) read only
archive members named `runs/*/record.json`. They do not extract or inspect
exploit source, payloads, target binaries, conversations, traces, or other
submission artifacts. The figure generator produces both SVG and PNG versions.

1. [Primary endpoint forest plot](diagrams/01_primary_endpoint_forest.svg)
2. [Progress ladders](diagrams/02_progress_ladders.svg)
3. [Shared-backend dumbbell plot](diagrams/03_shared_backend_dumbbell.svg)
4. [Shared-target conversion](diagrams/04_shared_target_conversion.svg)
5. [Trial-specific prompting-strategy heatmap](diagrams/05_backend_strategy_delta_heatmap.svg)
6. [Tool-use composition](diagrams/06_tool_use_composition.svg)
7. [Conditional validator conversion](diagrams/07_conditional_conversion.svg)
8. [Resource empirical distributions](diagrams/08_resource_ecdfs.svg)
9. [Matrix coverage mosaic](diagrams/09_matrix_coverage_mosaic.svg)
10. [BroncoCTF milestones](diagrams/10_bronco_milestones.svg)
