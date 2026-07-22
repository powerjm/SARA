# SARA paper diagrams

This directory contains one clean or layered publication-oriented raster figure
for each of ten architecture subjects. The discarded contract, journal, and
blueprint variants have been removed.

The figures reflect ADRs 0010–0012: text-format action recovery, provider-valid
backend wire formats, and the bounded retry nudge. All figures were checked for
label and control-flow accuracy against the current working tree.

## System architecture

![Layered system architecture](system_architecture/system_architecture_a_layered.png)

## Experiment data flow

![Layered experiment data flow](experiment_data_flow/experiment_data_flow_a_layered.png)

## Experiment configuration

![Clean experiment configuration](experiment_configuration/experiment_configuration_clean.png)

## Agent loop

![Clean agent loop](agent_loop/agent_loop_a_clean_flow.png)

## Zero-shot prompting

![Clean zero-shot prompting flow](zero_shot/zero_shot_a_clean_flow.png)

## Chain-of-thought prompting

![Clean chain-of-thought prompting flow](chain_of_thought/chain_of_thought_a_clean_flow.png)

## ReAct prompting

![Clean ReAct workflow](react/react-a-vector-workflow.png)

## MAJORCA prompting

![Clean MAJORCA workflow](majorca/majorca-a-vector-workflow.png)

## Corpus sources and provenance

![Clean corpus-provenance workflow](corpus_sources/corpus-sources-a-vector-workflow.png)

## Swappable LLM backends

![Layered swappable LLM backends](llm_backends/llm_backends_a_layered.png)

## Prompt specification

The figures use the built-in image-generation path with the
`infographic-diagram` use case. The shared specification requests a landscape
academic-paper figure, restrained dark-on-light colors, crisp readable
typography, exact minimal labels, generous whitespace, and no logos, watermark,
blueprint grid, journal treatment, contract bands, decorative illustration,
gradients, or 3D effects.

Subject-specific content:

- **System architecture:** four layers, the `RunRecord` contract, validator as
  sole execution path, action parsing, retry nudges, and provider-valid wire
  translation.
- **Experiment data flow:** binary × backend × strategy, five replicates per
  cell, one `RunRecord` per run, `ANY`-success and median aggregation rules,
  refusal separation, paired statistics, and findings.
- **Experiment configuration:** the exact `experiments.yaml` matrix—10 binaries,
  11 backend handles, four strategies, five replicates, 440 cells and 2,200
  planned runs—plus per-run limits, hosted-backend cost caps, output directory,
  and overrides.
- **Agent loop:** `INGEST → ENUMERATE → REASON`, baseline enumeration as user
  context, native or parsed text actions, a maximum-two-nudge `REASON` self-loop,
  submit/give-up through `PROPOSE`, and budget/refusal through `VALIDATE`.
- **Zero-shot:** task, constraints, and tool descriptions without exemplars or a
  reasoning scaffold; native/parsed JSON calls; bounded no-tool nudges.
- **Chain-of-thought:** `THOUGHT → ACTION`; native calls or `Action:` text parsed
  by `parse_text_actions`; normalized tool result and assessment loop.
- **ReAct:** `THOUGHT → ACTION → OBSERVATION`, with native/text action
  normalization and harness-supplied observations.
- **MAJORCA:** its four original stages and DAG construction, wrapped—not
  modified—by native/parsed JSON dispatch and bounded nudge behavior.
- **Corpus provenance:** high-leakage CGC/cb-multios (4), medium-leakage
  re-authored ISP RAS rop-benchmark targets (5), and low-leakage BroncoCTF
  Proper Pwning (1), followed by build/pin, verification, validation, and the
  universal `HELLO SANS` marker.
- **LLM backends:** stable `Backend` ABC, lazy registry, premium/open-weight/
  unrestricted categories, provider-specific wire translation, LM Studio as the
  shared local transport, versioned pricing, and normalized `ChatResponse` plus
  `CostRecord` output.
