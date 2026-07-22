# agent/

The agent loop: a LangGraph state machine that ingests a target binary,
enumerates ROP gadgets, reasons with a backend, proposes a candidate payload,
and hands it to the validator. Each node is a pure `AgentState -> AgentState`
function; the graph shape is fixed (ADR 0001), and later steps expand the tool
layer and prompting strategies without changing it.

## The graph

```
INGEST  ->  ENUMERATE  ->  REASON  ->  PROPOSE  ->  VALIDATE
                ^                |          |            |
                |                v          v            v
                +----------------+     payload.bin   success / fail
```

`REASON` runs one backend chat round, then `route_after_reason` decides where to
go: a `submit_payload` tool call goes to `PROPOSE`; any other tool call loops
back through `ENUMERATE` to dispatch it; a terminal flag (budget exhausted or
refusal) or an already-committed payload goes straight to `VALIDATE`. Budgets
(reason-round count, token budget, wall-clock cap) bound the loop.

The validator is the **only** component that executes payloads (ADR 0002); the
agent's tools are inspect-only. The canonical `(Outcome, FailureMode)` for a run
is decided by `validator.classifier.classify`, not by the agent's own claims.

## Files

- `state.py` — `AgentState` (threaded between nodes; kept small and
  serializable, since LangGraph rebuilds it from channel values each superstep),
  plus `BinaryContext`, `Message`, `ToolObservation`.
- `graph.py` — the nodes, the router, `build_graph`, and the `run_agent` /
  `build_run_record` orchestration that turns a finished run into a `RunRecord`.
  Per-run dependencies (backend, tool layer, budgets, validator config) are bound
  into the nodes via `AgentConfig`.
- `tools.py` — `ToolLayer`, mapping the agent's tool calls onto the MCP-backed
  tool functions. Advertises `enumerate_gadgets` (dispatched here) and the
  terminal `submit_payload` (materialized by the propose node). Injectable so
  tests can swap in a canned enumerator and run the loop without the ROPgadget
  CLI.
- `prompts/` — prompting strategies, the experiment's independent variable.

## Prompting strategies

Each strategy is a named bundle of system prompt, tool-use guidance, and task
template, registered in `prompts/STRATEGIES` and resolved by the CLI's
`--strategy` flag. Adding one means adding a module and registering it; the graph
does not change.

- `zero_shot` — minimal scaffolding, no exemplars (Brown et al., 2020).
- `chain_of_thought` — explicit reasoning before each action (Wei et al., 2022).
- `react` — Thought/Action/Observation scratchpad loop (Yao et al., 2022).
- `majorca` — staged code-reuse chain generation (Nurmukhametov et al., 2021).

## Tracing

When `run_agent` is given a `trace_sink`, the graph is streamed and the sink
receives one small event per node transition (the harness writes these to
`trace.jsonl`). Trace lines are deliberately compact — full per-iteration
artifacts are reconstructable from the persisted record and payload and do not
belong inline.
