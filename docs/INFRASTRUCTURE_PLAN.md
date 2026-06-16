# Infrastructure plan

Companion to `Powers_AgentInfrastructurePlan.docx`. This file is the in-repo, lightweight reference. The Word document is the authoritative version that goes into the thesis package; this file repeats the architectural rationale so changes to the codebase have a justification right next to the code.

> If you change architecture (e.g., swap orchestration, add a tool category, change the validator boundary), update **both** files.

## Goals

1. **Comparability.** Every backend runs against the same binaries with the same tool layer under the same hardware budget. Differences in outcome must be attributable to the backend.

2. **Replayability.** A run record + trace + payload must allow another researcher to re-execute the validator step and confirm the outcome without re-paying for LLM tokens.

3. **Failure-mode visibility.** A failure is not opaque. The trace, the final state, and the validator output combine to point at one of a small set of failure modes that the analysis pipeline cross-tabulates by backend.

## Four-layer architecture

```
+--------------------------------------------------------------------+
|  Layer 4 — Validation & Telemetry                                  |
|  Docker sandbox runner, outcome classifier, RunRecord persistence  |
+--------------------------------------------------------------------+
|  Layer 3 — MCP tool layer                                          |
|  Per-tool MCP servers: ROPgadget, Ghidra, radare2, Ropper,         |
|  pwntools, GDB inspect. Uniform JSON schemas; per-call timeouts.   |
+--------------------------------------------------------------------+
|  Layer 2 — Backend swap layer                                      |
|  Backend ABC + Anthropic, OpenAI, Google, LM Studio implementations|
+--------------------------------------------------------------------+
|  Layer 1 — Orchestration                                           |
|  LangGraph state machine: ingest -> enumerate -> reason ->         |
|  propose -> validate                                               |
+--------------------------------------------------------------------+
```

Each layer presents a narrow interface to the one above. Swapping the backend does not touch the tool layer; swapping a tool does not touch the agent loop; swapping the orchestrator (e.g., from LangGraph to a hand-roll) does not touch the validator.

## Phased build sequence

| Phase | What lands | Why this order |
|------:|-----------|----------------|
| 0 | Repo, lab env, pinned tooling | Nothing else builds without this. |
| 1 | Single-tool spike: ROPgadget MCP + Anthropic backend + LangGraph skeleton + validator stub | Smallest end-to-end pipeline that proves the four layers compose. |
| 2 | Full tool suite as MCP servers | Highest-risk integrations; surface format issues early. |
| 3 | Backend swap layer (OpenAI, Google, LM Studio) | Now that one backend works, generalize. |
| 4 | Corpus pipeline + verification | Need the tool layer working before fingerprinting documented chains. |
| 5 | Full run harness, batch CLI, persistent run records | Once Phases 1–4 are stable, productionise. |
| 6 | Statistical analysis notebooks | Driven by real records; can stub on synthetic data earlier. |
| 7 | Hardening, replication snapshot | Pin everything, write the reproduction guide. |

## Key design decisions

- **LangGraph over plain LangChain.** Explicit state machine; states are named and can be referenced from failure-mode coding. See `docs/adr/0001-use-langgraph.md`.
- **MCP servers per tool, not one wrapper.** Each tool's schema is independently reviewable. A bug in one server can't poison the others.
- **Cost in the backend, not the harness.** Each provider has its own pricing table and tokenizer; centralising cost would require the harness to know every provider's quirks. Backends emit a `CostRecord` directly.
- **Validator is the only execution path.** The agent's tools include GDB *inspect*, but never *run*. All execution goes through `validator.runner` with the hardened sandbox.
- **N≥1 runs per cell, collapsed by anyOf-success.** Documented in `analysis/aggregate.py`. A cell counts as success if any of its runs succeeded; medians are used for time / cost / iterations.

## Where the experiment's independent and dependent variables live

| Variable | Code location |
|----------|---------------|
| Backend category | `harness.record.BackendCategory` |
| Prompting strategy | `harness.record.PromptingStrategy`, `agent/prompts/` |
| Outcome | `harness.record.Outcome` |
| Failure mode | `harness.record.FailureMode` |
| Wall-clock | `RunRecord.wall_clock_seconds` |
| Token cost | `RunRecord.cost.usd` |
| Hardware cost | `RunRecord.cost.hardware_usd_estimate` |
| Iteration count | `RunRecord.iterations` |

If you add a variable to the experiment, add it here and in the schema in the same commit.
