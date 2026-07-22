# ADR 0012 — Bounded retry-nudge when a reason turn emits no tool call

Status: Accepted (Step 8).

Relates to ADR 0001 (LangGraph) — adds a bounded `reason -> reason` self-loop
edge (no new node); and ADR 0010 (text-action parsing), which this complements.

## Context

The agent makes progress only by emitting a tool call: `route_after_reason`
inspects the assistant turn's `tool_calls` and routes a `submit_payload` to
`propose`, any other tool call back through `enumerate`, and — originally —
**anything else straight to give-up** (`propose -> validate -> agent_gave_up`).

So a reason turn that produced prose with no tool call ended the run immediately,
on the **first** turn. The Step-8 smoke showed this is a common failure shape for
open/uncensored models: they reason out loud, or half-format an action, before
acting. ADR 0010 recovers *text-formatted* actions, but a model that emits pure
prose (no `Action:` line, no JSON call) still dead-ended with no chance to
correct — the harness under-measured capability rather than measuring it.

Real agent frameworks handle this with a "no tool call detected — please call a
tool" message and another turn. The model already receives the full tool specs
every round (the give-up was never about not knowing the tools), so a prod is
usually enough.

## Decision

**On a no-tool-call, no-committed-payload reason turn, loop back and nudge the
model to call a tool — a bounded number of times — before giving up.**

- `route_after_reason` returns `"reason"` (a self-loop) instead of `"propose"`
  while `state.nudge_count < config.max_nudges`; once the budget is spent it
  returns `"propose"` (unchanged give-up).
- On re-entry, `node_reason` appends a `user` nudge ("You did not call a tool …
  call `enumerate_gadgets` or `submit_payload` …") and increments
  `state.nudge_count` before the next backend call.
- Budget: `AgentConfig.max_nudges` (default **2**), surfaced through
  `RunSettings.max_nudges` / `RUN_MAX_NUDGES`. **0 restores the original one-shot
  give-up.** The existing per-run `max_iterations` / token / wall-clock guards
  still bound the loop.

No new graph node — only a new conditional edge value — so the control flow stays
inspectable/replayable (ADR 0001).

## Consequences

- Fewer spurious `agent_gave_up` outcomes; a model that forgets to call a tool on
  turn one gets up to `max_nudges` corrective turns. Combined with ADR 0010 this
  is what lets the reasoning strategies and open-weight models be measured on
  capability rather than first-turn formatting.
- Give-up now costs up to `max_nudges + 1` reason turns (more tokens/latency per
  failed run) and adds nudge `user` turns to the transcript. Tests that assert the
  one-shot give-up path set `max_nudges=0`.
- Outcome distributions shift for runs that previously gave up on turn one; like
  ADR 0010, pre-/post-change runs are not directly comparable — a provenance note
  for the replication snapshot. No `RunRecord` schema change.
- `max_nudges` is a knob, not a truth: too high wastes budget on models that will
  never call a tool. Default 2 is deliberately small.
