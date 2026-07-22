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

## Build sequence — the eight steps

Development followed one linear plan: eight ordered **Steps**, each building one
subsystem at a time and shipped **complete** (real code, real tests, no leftover
stubs) before the next began. The full step-by-step record — What / Why /
Done-when and what actually landed — is in
[`SARA_DEVELOPMENT_HISTORY.md`](SARA_DEVELOPMENT_HISTORY.md); Steps 0–7 are done
and Step 8 (run for record) is in progress.

| Step | What lands | Why this order |
|-----:|-----------|----------------|
| 0 | Repo, lab env, pinned tooling | Nothing else builds or runs until the toolchain is proven on the target platform. |
| 1 | Test data: the `sample_overflow` fixture binary + the deterministic synthetic dataset | Every integration test and the whole analysis pipeline need real artifacts to run against. |
| 2 | ROPgadget MCP server (the worked-example tool) | Until one tool is real, the agent can't enumerate gadgets and no other tool has a template to copy. |
| 3 | Validator sandbox (the single execution path) | No run yields a real outcome until the one component allowed to execute payloads works. |
| 4 | Agent loop, end-to-end on a `FakeBackend` | The spine of the apparatus; a fake backend makes the whole loop testable without spending money. |
| 5 | `sara run` + `sara batch`: harness, batch CLI, persistent run records | Once the loop runs, productionise it into the commands that produce the dataset. |
| 6 | Statistical analysis notebooks | Driven by records; can run on the synthetic dataset until real runs exist. |
| 7 | Every backend + every tool (OpenAI, Google, LM Studio; radare2, Ropper, pwntools, GDB, Ghidra) | The cross-backend, multi-tool framing can't be tested with one backend and one tool. |
| 8 | Run for record: hardening, CI/quality gates, real infra, replication snapshot | Pin everything and make the chosen environment reproducible for the runs the thesis cites. |

## Key design decisions

- **LangGraph over plain LangChain.** Explicit state machine; states are named and can be referenced from failure-mode coding. See `docs/adr/0001-use-langgraph.md`.
- **MCP servers per tool, not one wrapper.** Each tool's schema is independently reviewable. A bug in one server can't poison the others.
- **Cost in the backend; prices in one file.** Each backend does its own token accounting and cost math and emits a normalised `CostRecord`, so the harness never learns any provider's quirks. The *rates* are **not** hard-coded per backend: they live in one versioned `backends/pricing.yaml`, and each run embeds the snapshot it used so a recorded cost stays auditable — rates are refreshed deliberately, never fetched at run time. See [`adr/0007-pricing-source-and-provenance.md`](adr/0007-pricing-source-and-provenance.md).
- **Validator is the only execution path.** The agent's tools include GDB *inspect*, but never *run*. All execution goes through `validator.runner` with the hardened sandbox. See [`adr/0002-validator-boundary.md`](adr/0002-validator-boundary.md).
- **N runs per cell, collapsed by anyOf-success.** The aggregation rule works for any N≥1, but the runs for record use **N = 5** replicates (Step-5 decision — tighter Wilson intervals and more stable medians for the paired tests). Documented in `analysis/aggregate.py`: a cell counts as success if any of its runs succeeded; medians are used for time / cost / iterations.

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
