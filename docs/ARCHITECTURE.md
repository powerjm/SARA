# SARA architecture

A map of the whole apparatus: what each part does, how data moves through it, and
the invariants that hold it together. This is the **"what / how it fits"**
reference; the **"why it is this way"** rationale lives in
[`INFRASTRUCTURE_PLAN.md`](INFRASTRUCTURE_PLAN.md) and the
[ADRs](adr/). For how it was built step by step, see
[`SARA_DEVELOPMENT_HISTORY.md`](SARA_DEVELOPMENT_HISTORY.md); to re-run it, see
[`REPRODUCTION.md`](REPRODUCTION.md).

## What SARA is

SARA (*Sans Agentic Rop Analysis*) is the experimental apparatus for a SANS.edu
thesis on whether LLM agents can build Return-Oriented Programming (ROP) exploit
chains against intentionally-vulnerable binaries. It is a **research instrument,
not a product**: its job is to produce reproducible statistical results, so the
design optimises for comparability, replayability, and failure-mode visibility
over feature velocity.

Ethical scope is enforced by design and is non-negotiable (see
[`../README.md`](../README.md)): educational/CTF/DARPA-CGC/ISPRAS targets only,
proof-of-concept payloads only, and a **single execution path** (the validator)
so no other component can run a payload.

## The experiment, in one picture

SARA runs an **experiment matrix**. Each cell is a triple

```
(binary, backend, prompting_strategy)
```

run **N = 5** independent times (replicates; ADR-adjacent Step-5 decision). Every
single run emits exactly one `RunRecord`. Data flows in **one direction** — no
component reads back upstream:

```
   experiment matrix (binary × backend × strategy)
            │   one cell, run N times
            ▼
   agent run ──────────────► RunRecord  ({record.json, trace.jsonl, payload.bin})
   (LangGraph loop +              │        one per run, atomically persisted
    backend + tools +             │
    validator)                    ▼
                          aggregation ──► CellSummary  (collapse N runs → one cell)
                                    │       success = ANY run succeeded;
                                    │       time/cost/iterations = median
                                    ▼
                              statistics ──► Findings  (paired tests, effect sizes,
                                                        Wilson intervals → the thesis)
```

The `RunRecord` is the seam between "running experiments" and "analysing them."
Everything upstream serialises *into* it; everything downstream deserialises
*from* it.

## Four layers

Each layer exposes a narrow interface to the one above, so a swap at one layer
does not ripple into the others (rationale and the layer diagram are in
[`INFRASTRUCTURE_PLAN.md`](INFRASTRUCTURE_PLAN.md#four-layer-architecture)).

| Layer | Directory | Responsibility |
|------:|-----------|----------------|
| 1 — Orchestration | [`agent/`](../agent) | LangGraph state machine encoding the methodology |
| 2 — Backends | [`backends/`](../backends) | Swappable LLM providers behind one ABC |
| 3 — Tools | [`mcp_servers/`](../mcp_servers) | Per-tool MCP servers wrapping binary-analysis tools |
| 4 — Validation & telemetry | [`validator/`](../validator), [`harness/`](../harness) | Sandbox execution, outcome classification, `RunRecord` persistence |

## The schema is the contract — `harness/record.py`

This is the canonical source of truth. The core `StrEnum`s — `Outcome`,
`FailureMode`, `BackendCategory`, `PromptingStrategy` — plus `RunRecord` (and its
nested `CostRecord` / token / validator-output models) define the entire
experiment. Every emitter serialises through these models; the analysis pipeline
deserialises through them. `RunRecord` enforces the outcome/failure-mode
invariants **at construction time** (e.g. a success carries no failure mode; a
failure must name one).

Changing a field here is a **versioning event**: bump `schema_version` and add a
migration note. This is a high-review-cost file (see `CONTRIBUTING.md`).

The independent vs dependent variables and where each lives in the schema are
tabulated in
[`INFRASTRUCTURE_PLAN.md`](INFRASTRUCTURE_PLAN.md#where-the-experiments-independent-and-dependent-variables-live).

## Layer 1 — the agent loop (`agent/`)

[`agent/graph.py`](../agent/graph.py) builds a LangGraph state machine whose
shape **is** the methodology:

```
INGEST → ENUMERATE → REASON → PROPOSE → VALIDATE
                       │
                       └── tool call ──► back to ENUMERATE   (route_after_reason)
                       └── submit_payload ──► PROPOSE
                       └── gives up / budget hit ──► terminate
```

- Each node is a pure `AgentState → AgentState` function.
- `INGEST` summarises arch/protections/entry; `ENUMERATE` dispatches the tool
  layer; `REASON` calls `backend.chat`, enforces the token / wall-clock /
  iteration budgets, and detects refusal; `PROPOSE` writes `payload.bin` and the
  ordered candidate chain; `VALIDATE` calls the validator and hands off to the
  classifier.
- `AgentState` ([`agent/state.py`](../agent/state.py)) is kept small and
  serialisable. Large per-iteration artifacts go to the `trace.jsonl` the harness
  writes (one line per node transition), **not** into state.
- Per-run dependencies (backend, `ToolLayer`, validator config, budgets, output
  dir) are bound in by `build_graph` via `AgentConfig`. The graph **shape is
  fixed**; prompting strategies (`agent/prompts/`) and the tool catalogue expand
  without changing it.

LangGraph was chosen for inspectable, replayable control flow
([ADR 0001](adr/0001-use-langgraph.md)).

## Layer 2 — backends (`backends/`)

[`backends/base.py`](../backends/base.py) defines the `Backend` ABC: `chat()` +
`count_tokens()`, with **cost calculation baked into each backend** so the
harness only ever sees a normalised `CostRecord`. Refusal detection lives on the
base class (`detect_refusal`, metadata-first: Anthropic `stop_reason` /
OpenAI-family `finish_reason`, keyword fallback), so every backend inherits it.

[`backends/registry.py`](../backends/registry.py) is the single source of truth
for known backends; the CLI `--backend` flag resolves through `registry.get()`.
Registration is **explicit** (no import side-effects beyond `_register_defaults`)
and **lazy** (factories are lambdas), so importing the module needs no API keys.
Implemented: Anthropic, OpenAI, Google (all `PREMIUM`), and LM Studio (serving
both `OPEN_WEIGHT` and `UNRESTRICTED` locally). The category boundary is
safety-alignment status, declared a priori per model
([ADR 0005](adr/0005-backend-categories.md)). Backends honour `temperature` /
`seed` for determinism.

## Layer 3 — tools (`mcp_servers/`)

Each binary-analysis tool is its **own** MCP stdio server, so one tool's schema
is independently reviewable and a bug in one can't poison the others. The pattern
(worked example: [`mcp_servers/ropgadget/server.py`](../mcp_servers/ropgadget/server.py)):

- a **pure, testable function** (e.g. `enumerate_gadgets`) that does the parsing /
  shell-out, unit-tested without the MCP SDK; plus
- a thin `serve()` layer that wires the function into an MCP server.

Every server enforces a per-call timeout and an output budget (truncates and sets
a `truncated` flag). Servers: ROPgadget (Step 2), and radare2, Ropper, pwntools,
GDB, Ghidra (Step 7). **GDB is inspect-only** — execution commands are rejected
before gdb is invoked, preserving the single-execution-path invariant
([ADR 0002](adr/0002-validator-boundary.md)). Ghidra uses PyGhidra
([ADR 0004](adr/0004-ghidra-bridge.md)). The agent reaches tools through the
injectable `ToolLayer` in [`agent/tools.py`](../agent/tools.py); `submit_payload`
is the agent's terminal action and is materialised by `PROPOSE`, not dispatched
as a tool.

## Layer 4 — validator & telemetry (`validator/`, `harness/`)

**The validator is the only component that executes payloads** (ADR 0002).

- [`validator/runner.py`](../validator/runner.py) runs a candidate payload
  against a binary inside a locked-down Docker sandbox: `network_disabled`,
  read-only rootfs, non-root uid 1500, mem/pids limits, all caps dropped,
  `no-new-privileges`, a host-side wall-clock cap, and removal in a `finally:`
  even on timeout. The binary and payload are copied into a read-only `/work`
  mount under fixed names, so the run command is a constant with **no
  host-controlled strings** (no shell-injection surface). A Docker exception on
  launch is folded into a non-success result rather than raised, so one bad
  container can't abort a batch.
- The **chain fingerprint** is the *ordered* gadget-address sequence; a reordered
  chain is a different chain ([ADR 0003](adr/0003-chain-fingerprint.md)).
  `matched_documented_chain` is set iff the candidate's fingerprint equals the
  corpus-documented one.
- [`validator/classifier.py`](../validator/classifier.py) is the **single
  function** deciding the canonical `(Outcome, FailureMode | None)` for a finished
  run. High-review-cost: add a unit test for any new branch.

The harness ([`harness/`](../harness)) wraps the loop into runnable commands:
`run_one` (pure callable) → atomic `{record.json, trace.jsonl, payload.bin}`
persistence (assemble in `.partial-<id>/`, `os.replace` into place);
`harness/matrix.py` (resumable batch, **per-backend** USD cost cap, `--dry-run`
plan + estimate); `harness/corpus.py` (manifest → `BinarySpec`); and the
`sara run / batch / verify / replay` CLI ([`harness/cli.py`](../harness/cli.py)).

## Corpus (`corpus/`)

[`corpus/manifest.yaml`](../corpus/manifest.yaml) is the metadata catalog (in
git); the binaries themselves are gitignored. Each entry records source, sha256,
protections, difficulty tier, documented exploit/gadget addresses,
`success_marker`, license, and training-data-leakage risk. `binary_id` in a
`RunRecord` is a **foreign key** into this manifest. `corpus/scripts/`
fetches (`fetch.py`), builds-from-source where needed (`build.py`, e.g. the CGC
ports), and verifies (`verify.py`, confirms each documented exploit still fires
in the sandbox). **Runs for record require a fully-populated, verified manifest —
not the placeholder entries.**

## Analysis (`analysis/`)

- [`analysis/aggregate.py`](../analysis/aggregate.py) collapses raw `RunRecord`s
  into per-cell `CellSummary`s. The collapsing rule: a cell is a **success iff
  ANY run succeeded**; time/cost/iterations use the **median** across runs;
  all-refused cells are reported separately from failures. High-review-cost: this
  rule changes every report.
- [`analysis/stats.py`](../analysis/stats.py) implements the paired tests
  (Cochran's Q, McNemar's, Friedman's, Wilcoxon, Wilson interval, Bonferroni,
  effect sizes) over the paired-by-binary matrices `aggregate.py` builds.
- [`analysis/load_runs.py`](../analysis/load_runs.py) loads finalised records, or
  falls back to the deterministic synthetic dataset
  ([`analysis/synthetic.py`](../analysis/synthetic.py)) so the notebooks run
  before real data exists. The seven notebooks (`analysis/notebooks/01..07`) are
  thin load → aggregate → stats → figure → Markdown orchestrators.

## Two run environments

The apparatus runs **identically** local or cloud — same code, same Docker
validator, same `RunRecord` output. Only the host and `.env` differ.

- **Local** (default): one Ubuntu 26.04 host. API backends via keys in `.env`;
  open-weight / unrestricted models via a local LM Studio endpoint.
- **Cloud**: the same stack on a reproducible VM from [`infra/packer/`](../infra/packer)
  (the pinned image) + [`infra/terraform/`](../infra/terraform) (the instance). A
  GPU instance is needed **only** to run local models in the cloud; API-only
  backends run on a CPU instance.

`.env` (`RUN_OUTPUT_DIR`, `VALIDATOR_IMAGE`, backend keys/endpoints) is the only
thing that differs between a laptop and a cloud VM.

## Invariants (keep these true)

1. **One execution path.** Only `validator.runner` runs a payload. GDB is
   inspect-only. Adding a tool must not add an execution path. (ADR 0002)
2. **The schema is the contract.** Any change to `harness/record.py` bumps
   `schema_version` and updates every serialiser/deserialiser in the same commit.
3. **One outcome-truth function.** `validator.classifier.classify` is the only
   place `(Outcome, FailureMode)` is decided.
4. **`StrEnum`, not string literals**, for outcomes / failure modes / strategies /
   categories.
5. **Cost lives in the backend.** The harness sees only normalised `CostRecord`s.
6. **State stays small.** Large artifacts go to `trace.jsonl`, not `AgentState`.
7. **Each step ships complete** — no stubs, real tests; `make format && make lint
   && make test` before every commit.

## Where to read next

- [`SARA_DEVELOPMENT_HISTORY.md`](SARA_DEVELOPMENT_HISTORY.md) — how it was built,
  step by step, with each step's acceptance criteria.
- [`INFRASTRUCTURE_PLAN.md`](INFRASTRUCTURE_PLAN.md) — the architectural rationale.
- [`REPRODUCTION.md`](REPRODUCTION.md) — the full run procedure.
- [`REPLICATION_SNAPSHOT.md`](REPLICATION_SNAPSHOT.md) — the reproducibility bundle.
- [`adr/`](adr/) — the numbered, append-only architecture decisions.
