# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`sara` (Sans Agentic Rop Analysis) is the experimental apparatus for a SANS.edu master's thesis on using LLM agents to build Return-Oriented Programming (ROP) exploit chains against intentionally-vulnerable binaries. It is a **research instrument, not a product**: the goal is reproducibility of published statistical results, not feature velocity. The code was built one subsystem at a time per the eight-step plan in `docs/SARA_DEVELOPMENT_HISTORY.md` — each step ships **complete** (real implementation, real tests, no leftover `TODO` stubs) before the next begins. Steps 0–7 are done; all subsystems are real (no stubs). Step 8 (run for record: hardening, CI gates, infra, replication snapshot) remains.

**Ethical scope is enforced by design** (see `README.md`): educational/CTF targets only, proof-of-concept payloads only. The validator is the single component that executes payloads; do not add execution paths elsewhere (ADR 0002).

## Commands

```bash
make bootstrap     # create .venv, install -e ".[dev,analysis]", install pre-commit
make test          # pytest -q --cov=. --cov-report=term-missing
make lint          # ruff check .
make typecheck     # mypy . (strict)
make format        # ruff format + ruff check --fix
make sandbox-build # docker build -f Dockerfile.sandbox -t sara-sandbox:latest .

# Run a single test
.venv/bin/pytest tests/test_record_schema.py -q
.venv/bin/pytest tests/test_record_schema.py::test_name -q

# CLI entry point (installed as `sara`, or `python -m harness.cli`)
sara run    --binary sample-overflow --backend claude-sonnet --strategy zero_shot
sara batch  --config experiments.yaml
sara verify --binary sample-overflow        # reproduce documented exploit (corpus-truth)
sara replay --run-id <uuid>                 # re-run validator on a stored payload
```

Requires Python **3.14+** (targets Ubuntu 26.04 LTS). `pytest` runs with `filterwarnings = ["error"]` and `asyncio_mode = "auto"`. mypy is `strict` but advisory on CI (stubs still firming up); ruff is enforced. The `binary-tools` extra (pwntools, r2pipe) needs native libs and is installed only on the lab host — never in CI.

## Architecture

The system runs an experiment matrix: each cell is a `(binary, backend, prompting_strategy)` triple, run N≥1 times, producing one `RunRecord` per run. The data flows in one direction: **agent run → run record → aggregation → statistics**.

### The schema is the contract — `harness/record.py`

This is the canonical source of truth. Every component that emits run data serializes through these Pydantic models; the analysis pipeline deserializes through them. The core enums (`Outcome`, `FailureMode`, `BackendCategory`, `PromptingStrategy`) and `RunRecord` define the entire experiment. **Changing a field here is a versioning event**: bump `schema_version` and add a migration note in `docs/`. `RunRecord` enforces outcome/failure-mode invariants at construction time.

### Agent loop — `agent/` (LangGraph)

`agent/graph.py` builds a LangGraph state machine encoding the methodology:
`INGEST → ENUMERATE → REASON → PROPOSE → VALIDATE`, with `REASON` looping back to `ENUMERATE` on tool calls (routed by `route_after_reason`). Each node is a pure `AgentState → AgentState` function. `agent/state.py` holds `AgentState` — keep it small and serializable; large per-iteration artifacts go in the trace JSONL written by the harness, not in state. The graph shape is fixed; later steps expand the tool layer and prompting strategies (`agent/prompts/`) without changing it. LangGraph was chosen for inspectable/replayable control flow (ADR 0001).

### Backends — `backends/` (swappable LLM providers)

`backends/base.py` defines the `Backend` ABC: `chat()` + `count_tokens()`, with **cost calculation baked into each backend** so the harness only sees normalized `CostRecord` values. `backends/registry.py` is the single source of truth for known backends; the CLI `--backend` flag resolves through `registry.get()`. Registration is explicit (no import side-effects beyond `_register_defaults`) and lazy (factories are lambdas), so importing the module needs no API keys. Anthropic, OpenAI, Google, and LM Studio backends are all implemented (Step 7). Backends must honor `temperature`/`seed` for determinism.

### Tools — `mcp_servers/` (MCP servers wrapping binary-analysis tools)

Each tool (ropgadget, ghidra, radare2, ropper, pwntools, gdb) is its own MCP stdio server. ROPgadget is the worked example (Step 2); the rest (ghidra, radare2, ropper, pwntools, gdb) landed in Step 7. Pattern (see `mcp_servers/ropgadget/server.py`): a **pure testable function** (`enumerate_gadgets`) plus a thin `serve()` MCP layer — the split keeps parsing/shell-out logic unit-testable without the evolving MCP SDK. GDB is inspect-only; it cannot execute payloads.

### Validator — `validator/`

`validator/runner.py` executes a candidate payload against a binary inside a locked-down Docker sandbox (no network, read-only rootfs, non-root uid 1500, mem/pids limits, dropped caps, wall-clock timeout). It is the **only** component allowed to run payloads (ADR 0002). `validator/classifier.py` is the single function deciding the canonical `(Outcome, FailureMode|None)` for a finished run — add a unit test for any new branch.

### Corpus — `corpus/`

`corpus/manifest.yaml` is the metadata catalog (in git); binaries themselves are gitignored. Each entry records source, sha256, protections, difficulty tier, documented exploit/gadget addresses, `success_marker`, license, and training-data-leakage risk. `corpus/scripts/` has `fetch.py`/`verify.py`. `binary_id` in a `RunRecord` is a foreign key into this manifest.

### Analysis — `analysis/`

`analysis/aggregate.py` collapses raw `RunRecord`s into per-cell `CellSummary`s: a cell is a **success iff ANY run succeeded**; time/cost/iterations use the **median** across runs; all-refused cells are reported separately from failures. `analysis/stats.py` implements the paired statistical tests (Cochran's Q, McNemar's, Friedman's, Wilcoxon, Wilson interval, Bonferroni, effect sizes), consuming the paired-by-binary matrices that `aggregate.py` builds.

## Development record — `docs/SARA_DEVELOPMENT_HISTORY.md`

**Read this file before starting any implementation work.** It records the eight ordered **Steps**, each declaring What / Why / Done-when, the files it touches, and the decision it needed first. Steps 0–7 are complete (real code, real tests, no stubs); Step 8 (run for record: hardening, CI gates, infra, replication snapshot) remains.

**Hard rule: each step ships complete.** No `TODO` markers, no stubbed bodies, no placeholder returns left behind — real code with real tests, finished before the next step starts. Don't leave scaffolding "to fill in later."

**The eight steps:** 0 — environment (done). 1 — test data (fixture binary + synthetic dataset). 2 — ROPgadget MCP server. 3 — validator sandbox. 4 — agent loop on a `FakeBackend`. 5 — `sara run` + `sara batch`. 6 — analysis notebooks. 7 — every backend + every tool. 8 — run for record (hardened, reproducible, local or cloud). Baseline is **68 tests, all passing** — keep them green.

**Two run environments (Step 8 makes the chosen one production-ready):** the stack runs identically **local** (one Ubuntu 26.04 host; local models via LM Studio) or **cloud** (the pinned VM from `infra/packer/` + `infra/terraform/`). Only `.env` differs.

**Working agreement (every step; don't relax without an ADR):** `make test` + `make lint` + `make format` before any commit; new code without tests in `tests/test_<module>.py` blocks merge; tests use fakes/cassettes, never real API keys; schema changes bump `schema_version`; one ADR per non-obvious architectural call. New ADRs land with their step: 0003 chain-fingerprint (Step 3), 0004 ghidra-bridge and 0005 backend-categories (Step 7).

**Don't guess on non-obvious research-design calls — surface them for Jeff, don't pick one silently.** The Steps 0–7 decisions (chain-fingerprint, refusal detection, cost-cap policy, replicates-per-cell, difficulty-tier analysis, open-weight vs unrestricted boundary, Ghidra bridge) are all resolved — see the "Decisions made during development" table in `docs/SARA_DEVELOPMENT_HISTORY.md` and ADRs 0003–0005. Apply the same rule to any new ones Step 8 surfaces.

## Conventions

- **Type-annotate everything crossing a module boundary.** mypy is strict.
- **Use `StrEnum`, not string literals**, for outcome / failure-mode / strategy.
- Tests live in `tests/test_<module>.py`. Run `make format && make lint && make test` before a PR (CI runs the same).
- Avoid one-letter variables except canonical math (`k`, `n`, `i`, `j`).
- **High-review-cost files** (per `CONTRIBUTING.md`): `harness/record.py` (schema — versioning event), `analysis/aggregate.py` (collapsing rule — changes every report), `validator/classifier.py` (outcome truth). Treat changes here with extra care.
- Architectural decisions get a numbered, append-only ADR in `docs/adr/` — supersede, never edit. Read `docs/INFRASTRUCTURE_PLAN.md` before non-trivial changes (the "why is it this way?" rationale lives there).
