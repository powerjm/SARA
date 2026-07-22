# SARA paper-diagram candidates

This directory contains three publication-oriented raster variants for each of
nine architecture subjects. All figures were generated from the repository
implementation and documentation, then visually checked for label and flow
accuracy.

## Variant key

- **A — clean schematic:** direct, presentation-friendly vector-style flow.
- **B — journal figure:** denser conceptual or contract-oriented organization.
- **C — technical blueprint:** restrained drafting-grid treatment with numbered
  or strongly structured stages.

## System architecture

| A — layered | B — contract | C — blueprint |
|---|---|---|
| ![Layered system architecture](system_architecture/system_architecture_a_layered.png) | ![Contract-oriented system architecture](system_architecture/system_architecture_b_contract.png) | ![Blueprint system architecture](system_architecture/system_architecture_c_blueprint.png) |

## Experiment data flow

| A — layered | B — contract | C — blueprint |
|---|---|---|
| ![Layered experiment data flow](experiment_data_flow/experiment_data_flow_a_layered.png) | ![Contract-oriented experiment data flow](experiment_data_flow/experiment_data_flow_b_contract.png) | ![Blueprint experiment data flow](experiment_data_flow/experiment_data_flow_c_blueprint.png) |

## Agent loop

| A — clean flow | B — journal process | C — blueprint |
|---|---|---|
| ![Clean agent loop](agent_loop/agent_loop_a_clean_flow.png) | ![Journal-style agent loop](agent_loop/agent_loop_b_journal_process.png) | ![Blueprint agent loop](agent_loop/agent_loop_c_blueprint.png) |

## Zero-shot prompting

| A — clean flow | B — journal comparison | C — blueprint |
|---|---|---|
| ![Clean zero-shot prompting flow](zero_shot/zero_shot_a_clean_flow.png) | ![Journal-style zero-shot prompting comparison](zero_shot/zero_shot_b_journal_comparison.png) | ![Blueprint zero-shot prompting](zero_shot/zero_shot_c_blueprint.png) |

## Chain-of-thought prompting

| A — clean flow | B — journal cycle | C — blueprint |
|---|---|---|
| ![Clean chain-of-thought prompting flow](chain_of_thought/chain_of_thought_a_clean_flow.png) | ![Journal-style chain-of-thought cycle](chain_of_thought/chain_of_thought_b_journal_cycle.png) | ![Blueprint chain-of-thought prompting](chain_of_thought/chain_of_thought_c_blueprint.png) |

## ReAct prompting

| A — vector workflow | B — journal loop | C — blueprint |
|---|---|---|
| ![ReAct vector workflow](react/react-a-vector-workflow.png) | ![ReAct journal loop](react/react-b-journal-loop.png) | ![ReAct blueprint](react/react-c-blueprint.png) |

## MAJORCA prompting

| A — vector workflow | B — journal DAG | C — blueprint |
|---|---|---|
| ![MAJORCA vector workflow](majorca/majorca-a-vector-workflow.png) | ![MAJORCA journal DAG](majorca/majorca-b-journal-dag.png) | ![MAJORCA blueprint](majorca/majorca-c-blueprint.png) |

## Corpus sources and provenance

| A — vector workflow | B — journal DAG | C — blueprint |
|---|---|---|
| ![Corpus provenance vector workflow](corpus_sources/corpus-sources-a-vector-workflow.png) | ![Corpus provenance journal DAG](corpus_sources/corpus-sources-b-journal-dag.png) | ![Corpus provenance blueprint](corpus_sources/corpus-sources-c-blueprint.png) |

## Swappable LLM backends

| A — layered | B — contract | C — blueprint |
|---|---|---|
| ![Layered swappable LLM backends](llm_backends/llm_backends_a_layered.png) | ![Contract-oriented swappable LLM backends](llm_backends/llm_backends_b_contract.png) | ![Blueprint swappable LLM backends](llm_backends/llm_backends_c_blueprint.png) |

## Prompt specification

All variants used the built-in image-generation path with the
`infographic-diagram` use case. The shared specification requested a landscape
academic-paper figure, restrained dark-on-light colors, crisp readable
typography, exact minimal labels, generous whitespace, and no logos, watermark,
decorative illustration, gradients, or 3D effects. Each subject's nodes and
edges were derived from `docs/ARCHITECTURE.md`, `docs/DIAGRAMS.md`, the four
prompt strategy modules, `corpus/manifest.yaml`, `corpus/README.md`, and the
backend interface and registry.

Subject-specific prompt content:

- **System architecture:** four layers, the `RunRecord` contract, corpus and
  harness inputs, analysis output, and validator as the sole payload-execution
  path.
- **Experiment data flow:** binary × backend × strategy, five replicates per
  cell, one `RunRecord` per run, `ANY`-success and median aggregation rules,
  refusal separation, paired statistics, and findings.
- **Agent loop:** `INGEST → ENUMERATE → REASON`, tool-call return to
  `ENUMERATE`, `submit_payload → PROPOSE → VALIDATE → RunRecord`, and
  budget/refusal termination.
- **Zero-shot:** task, constraints, and tool descriptions supplied directly to
  the model, explicitly without exemplars or a reasoning scaffold.
- **Chain-of-thought:** repeated
  `THOUGHT → ACTION → TOOL RESULT → ASSESSMENT` cycles ending in
  `submit_payload`.
- **ReAct:** `THOUGHT → ACTION → OBSERVATION` loop, with observations supplied
  by the harness and `submit_payload` as the terminal action.
- **MAJORCA:** ordered search, semantics, combination, and input-data stages;
  semantic catalog; four chain/DAG types; scheduling; stack frames; and the
  restricted-symbol arithmetic path.
- **Corpus provenance:** high-leakage CGC/cb-multios (4), medium-leakage
  re-authored ISP RAS rop-benchmark targets (5), and low-leakage BroncoCTF
  Proper Pwning (1), followed by build/pin, verification, validation, and the
  universal `HELLO SANS` marker.
- **LLM backends:** agent, `Backend` ABC methods, lazy registry, Anthropic,
  OpenAI, Google, and LM Studio adapters, versioned pricing, and normalized
  `ChatResponse` plus `CostRecord` output.
