# SARA architecture diagrams

Visual companions to [`ARCHITECTURE.md`](ARCHITECTURE.md) (the prose reference)
and [`INFRASTRUCTURE_PLAN.md`](INFRASTRUCTURE_PLAN.md) (the rationale). Every
diagram below is [Mermaid](https://mermaid.js.org/) — it renders inline on GitHub
and in most IDE Markdown previews.

- [Repository architecture](#repository-architecture)
  - [1. System architecture — four layers + the contract](#1-system-architecture--four-layers--the-contract)
  - [2. Experiment data flow (one direction)](#2-experiment-data-flow-one-direction)
  - [3. Agent loop — the LangGraph state machine](#3-agent-loop--the-langgraph-state-machine)
- [Test architecture](#test-architecture)
  - [4. Test-suite coverage map](#4-test-suite-coverage-map)
  - [5. Test doubles and the CI-vs-lab gating](#5-test-doubles-and-the-ci-vs-lab-gating)

---

## Repository architecture

### 1. System architecture — four layers + the contract

Each layer exposes a narrow interface to the one above, so a swap at one layer
does not ripple into the others. Two invariants are highlighted: the
**`RunRecord` schema is the single contract** (amber) that everything upstream
serialises into and everything downstream reads from, and the **validator is the
sole execution path** (red) — no other component may run a payload (ADR 0002).

```mermaid
flowchart TB
    CLI["<b>sara CLI</b><br/>run · batch · verify · replay<br/><i>harness/cli.py</i>"]

    subgraph HAR["Harness / telemetry (harness/)"]
        HARNESS["runner.py · matrix.py<br/>persistence.py · corpus.py"]
    end

    subgraph L1["Layer 1 · Orchestration (agent/)"]
        GRAPH["LangGraph state machine<br/>graph.py · state.py"]
        PROMPTS["Prompting strategies<br/>zero_shot · react<br/>chain_of_thought · majorca"]
        TOOLS["ToolLayer<br/>tools.py"]
    end

    subgraph L2["Layer 2 · Backends (backends/)"]
        BASE["Backend ABC<br/>chat() · count_tokens()<br/>detect_refusal()"]
        REG["registry.py"]
        PRICE["pricing.yaml + pricing.py"]
        PROV["anthropic · openai<br/>google · lmstudio"]
    end

    subgraph L3["Layer 3 · Tools (mcp_servers/, MCP stdio)"]
        ROP["ropgadget"]
        R2["radare2"]
        RPR["ropper"]
        PWN["pwntools"]
        GDB["gdb · inspect-only"]
        GHI["ghidra"]
    end

    subgraph L4["Layer 4 · Validation (validator/)"]
        RUNNER["runner.py<br/>Docker sandbox<br/>SOLE execution path"]
        CLASS["classifier.py<br/>(Outcome, FailureMode)"]
    end

    SCHEMA["<b>harness/record.py — RunRecord</b><br/>the contract<br/>record.json · trace.jsonl · conversation.jsonl · payload.bin"]
    CORPUS["corpus/manifest.yaml<br/>+ scripts: fetch · build · verify"]
    ANALYSIS["analysis/<br/>aggregate · stats<br/>load_runs · synthetic · notebooks"]

    CLI --> HARNESS
    CORPUS --> HARNESS
    HARNESS --> GRAPH
    GRAPH --> PROMPTS
    GRAPH -->|backend.chat| BASE
    GRAPH --> TOOLS
    TOOLS --> L3
    GRAPH -->|VALIDATE| RUNNER
    RUNNER --> CLASS
    BASE --> REG --> PROV
    BASE -.reads.-> PRICE
    HARNESS -->|persist| SCHEMA
    CLASS --> SCHEMA
    SCHEMA --> ANALYSIS

    classDef contract fill:#fde68a,stroke:#b45309,color:#111,stroke-width:2px;
    classDef exec fill:#fecaca,stroke:#b91c1c,color:#111,stroke-width:2px;
    class SCHEMA contract;
    class RUNNER exec;
```

### 2. Experiment data flow (one direction)

The matrix is `(binary × backend × strategy)`; each cell runs **N = 5** times and
emits one `RunRecord` per run. Data flows strictly left to right — no component
reads back upstream. The `RunRecord` is the seam between *running* experiments
and *analysing* them.

```mermaid
flowchart LR
    MATRIX["Experiment matrix<br/>binary × backend × strategy"]
    RUN["Agent run<br/>LangGraph + backend<br/>+ tools + validator"]
    REC["RunRecord ×N<br/>record.json · trace.jsonl<br/>conversation.jsonl · payload.bin"]
    AGG["aggregate.py"]
    CELL["CellSummary<br/>success = ANY run<br/>time/cost/iters = median<br/>all-refused reported apart"]
    STATS["stats.py"]
    FIND["Findings<br/>Cochran Q · McNemar · Friedman<br/>Wilcoxon · Wilson · Bonferroni"]
    THESIS["📄 Thesis results"]

    MATRIX -->|one cell, N runs| RUN --> REC
    REC -->|collapse N → 1| AGG --> CELL --> STATS --> FIND --> THESIS
```

### 3. Agent loop — the LangGraph state machine

The graph shape **is** the methodology. Each node is a pure
`AgentState → AgentState` function; `REASON` is the hub, routed by
`route_after_reason`. The shape is fixed — new prompting strategies and tools
extend the layers without changing it (ADR 0001). `ENUMERATE` seeds a baseline
gadget dump as *user context* (ADR 0011); Step 8 added a bounded `REASON→REASON`
nudge self-loop (ADR 0012) and text-format tool-call recovery (ADR 0010) without
adding nodes.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> INGEST
    INGEST --> ENUMERATE
    ENUMERATE --> REASON
    REASON --> ENUMERATE: tool call
    REASON --> PROPOSE: submit_payload
    REASON --> REASON: no tool call (nudge, bounded)
    REASON --> [*]: refusal / budget / gave up
    PROPOSE --> VALIDATE
    VALIDATE --> [*]: RunRecord

    note right of REASON
        route_after_reason
        backend.chat + token / wall-clock / iteration budgets
        refusal check (metadata + soft-text keywords)
        text-action recovery (ADR 0010) + nudge (ADR 0012)
    end note
    note right of VALIDATE
        validator.runner (sandbox)
        then classifier -> (Outcome, FailureMode)
    end note
```

---

## Test architecture

The suite is **379 tests** in [`tests/`](../tests), one
`tests/test_<module>.py` per subsystem, all green. Tests never touch real API
keys or the gitignored production corpus: LLM calls replay through a
`FakeBackend`, the corpus is a throwaway fixture, and the binary-analysis CLIs
are gated by markers so the tests **skip** (not fail) where a tool is absent.

### 4. Test-suite coverage map

Each box is a subsystem-under-test titled with the module(s) it exercises; the
nodes inside are the test files that cover it. Badges: **⬦** Hypothesis
property test, **🔧** tool-gated integration (skips on CI, runs on the lab host),
**🐳** Docker-gated (needs the daemon + built sandbox image).

```mermaid
flowchart TB
    subgraph S1["Schema / contract · harness/record.py"]
        a1["test_record_schema"]
        a2["test_record_schema_properties ⬦"]
        a3["test_fixtures_are_valid"]
    end
    subgraph S2["Agent · agent/graph.py · tools.py · prompts/"]
        b1["test_agent_graph"]
        b2["test_agent_graph_integration"]
        b3["test_agent_tools"]
        b4["test_prompts"]
    end
    subgraph S3["Backends · backends/*"]
        c1["test_backends"]
        c2["test_provider_backends"]
        c3["test_fake_backend"]
        c4["test_pricing"]
    end
    subgraph S4["Tools · mcp_servers/*"]
        d1["test_ropgadget_parser"]
        d2["test_ropgadget_integration 🔧"]
        d3["test_radare2_server 🔧"]
        d4["test_ropper_server 🔧"]
        d5["test_gdb_server 🔧"]
        d6["test_ghidra_server 🔧"]
        d7["test_pwntools_server"]
    end
    subgraph S5["Validator · validator/runner.py · classifier.py"]
        e1["test_validator_runner"]
        e2["test_validator_classifier"]
    end
    subgraph S6["Harness · harness/*"]
        f1["test_harness_runner"]
        f2["test_matrix"]
        f3["test_persistence"]
        f4["test_cli"]
        f5["test_verify"]
        f6["test_corpus_build"]
    end
    subgraph S7["Analysis · analysis/*"]
        g1["test_aggregate"]
        g2["test_stats"]
        g3["test_load_runs"]
        g4["test_synthetic"]
        g5["test_notebooks"]
    end
    subgraph S8["End-to-end"]
        h1["test_smoke_e2e 🔧 🐳"]
    end
```

### 5. Test doubles and the CI-vs-lab gating

**What stands in for production dependencies.** Every expensive or non-portable
dependency has a test double or fixture, all wired up by
[`tests/conftest.py`](../tests/conftest.py):

```mermaid
flowchart LR
    subgraph REAL["Production dependency"]
        RB["Real LLM APIs<br/>Anthropic · OpenAI · Google · LM Studio"]
        RT["Binary-analysis CLIs<br/>ROPgadget · r2 · ropper · gdb · Ghidra"]
        RD["Docker daemon<br/>+ sandbox image"]
        RC["Production corpus<br/>gitignored binaries"]
    end
    subgraph DBL["Test double / fixture (tests/)"]
        FB["FakeBackend<br/>fakes/backend.py<br/>scripted turns · cassette replay"]
        MK["requires_* markers<br/>+ conftest predicates"]
        MK2["mocked docker client<br/>/ importorskip('docker')"]
        FC["fixture_corpus<br/>throwaway manifest<br/>+ sample_overflow"]
    end
    RB -.replaced by.-> FB
    RT -.gated by.-> MK
    RD -.replaced / gated by.-> MK2
    RC -.replaced by.-> FC
```

Shared scaffolding those doubles draw on:
[`fakes/cassettes/*.jsonl`](../tests/fakes/cassettes) (recorded turns),
[`strategies.py`](../tests/strategies.py) (Hypothesis generators),
[`fixtures/run_records/*.json`](../tests/fixtures/run_records) (golden records),
and [`fixtures/binaries/sample_overflow`](../tests/fixtures/binaries) (the built
fixture binary + its `chain.json`).

**How the tool gate decides at collection time.** `pytest_collection_modifyitems`
in `conftest.py` maps each `requires_<tool>` marker to a presence predicate and
adds a skip when the tool is missing — so the same suite runs fully on the lab
host and skips the integration tests on CI, without ever failing there.

```mermaid
flowchart LR
    C["pytest collects an item"] --> Q{"has a<br/>requires_&lt;tool&gt; marker?"}
    Q -->|no| ALW["always runs<br/>unit · property · pwntools"]
    Q -->|yes| P{"tool present?<br/>on PATH · importable ·<br/>GHIDRA_INSTALL_DIR set"}
    P -->|"yes · lab host"| RUN["runs the integration test"]
    P -->|"no · CI"| SK["skipped, not failed"]

    classDef ok fill:#bbf7d0,stroke:#15803d,color:#111;
    classDef skip fill:#e5e7eb,stroke:#6b7280,color:#111;
    class RUN,ALW ok;
    class SK skip;
```
