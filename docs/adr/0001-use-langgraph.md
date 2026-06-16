# ADR 0001 — Use LangGraph for agent orchestration

Status: Accepted (Phase 0)

## Context

The agent loop must:

1. Be **inspectable** — failure-mode coding requires the ability to point at a named state when characterising a failure ("the agent looped in ENUMERATE without making progress").
2. Be **replayable** — given a stored trace, we must be able to re-execute the loop step-by-step without re-paying for tokens.
3. Be **deterministic in its control flow** — the model's outputs are stochastic, but the routing decisions on top of them must be code, not prompt-following.

## Decision

Use **LangGraph**.

We considered three options:

1. **Plain LangChain `AgentExecutor`** — Familiar; minimal setup.
2. **LangGraph** — Explicit state machine over a typed state object.
3. **Hand-rolled state machine** — Total control; more code.

We chose LangGraph because the state machine is a first-class object that can be inspected, replayed, and reasoned about during failure-mode coding.

## Consequences

**Positive:**

- The agent's transitions are explicit and named. Failure-mode coding can reference node names directly ("agent looped in ENUMERATE without making progress").
- State is a typed Pydantic-style dataclass, which makes the run-record schema and the in-memory state share definitions.
- Replay is cheap: feed the trace JSONL back through the graph node-by-node.

**Negative:**

- LangGraph is younger than LangChain and pin churn is higher. Mitigated by the pin in `pyproject.toml` and by keeping our use of LangGraph features minimal (state graph + conditional edges; no checkpointers, no human-in-the-loop interrupts).
- One more conceptual layer for new contributors. Mitigated by the diagram and explanation in `docs/INFRASTRUCTURE_PLAN.md`.

## Alternatives considered

- **Plain `AgentExecutor`** rejected because its loop is implicit. Replaying a failure means re-running the loop, not stepping through the recorded states.
- **Hand-rolled state machine** rejected because the experimental design is not novel enough in its control flow to justify the implementation cost.
