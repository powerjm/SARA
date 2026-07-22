# ADR 0014 — Iterative validation: execution is a repeatable, feedback-giving tool

Status: Accepted (Step 8).

Relates to ADR 0001 (LangGraph — this changes the graph *shape*: `validate` now
loops back to `reason` and a `finalize` node is added), ADR 0002 (validator is the
single execution path — still true; it is just called repeatedly), and ADR 0009
(the shell/marker success oracle — unchanged).

## Context

The original loop made `submit_payload` **terminal**: `reason → propose →
validate → END`. A run got exactly **one** execution, and the model **never saw
the result** — no exit code, no stdout, no "did the marker print." It could
iterate on *reasoning* (`reason ↔ enumerate`) but never test a candidate, watch
it crash, and revise.

Two problems followed. (1) With 5 replicates, each was a blind one-shot — "5
chances, each a first try" — which is not how exploit development, or agentic
tool use generally, works. (2) Because the model could not test anything, a
careful model kept reasoning to get it perfect in one shot and often **gave up
without ever submitting** (the validator never ran). The first goal-disclosed
runs showed exactly this: many turns of correct `execve("/bin/sh")` reasoning,
then `agent_gave_up` with no execution.

## Decision

**Make execution a repeatable tool. The agent runs candidate payloads against the
target as many times as it wants, each result fed back, until an execution prints
the marker (success), a ceiling trips, it refuses, or it gives up.** Confirmed
with Jeff: (1) the iterate loop is bounded by the **existing** ceilings
(`max_iterations` / token budget / wall-clock — no separate execution cap); (2)
success is the **first** execution that prints the marker.

Mechanically:

- `validate` no longer goes to `END`. `route_after_validate` sends a
  **non-success** execution back to `reason`; only success (or a ceiling tripped
  in `reason`) reaches the new `finalize → END`.
- Each `submit_payload` runs once (`propose` stages `payload.bin`, `validate`
  executes it) and the outcome is appended as a **tool result** keyed to the
  submit call — so the model sees "crashed / timed out / marker not found /
  anti-echo tripped" plus stdout/stderr excerpts, and the message stream stays a
  valid `tool_use → tool_result` pairing (ADR 0011).
- The per-turn budget guards in `reason` (`_assistant_round_count >=
  max_iterations`, token budget, wall-clock) bound the retry loop, since every
  execution is preceded by a `reason` turn. `recursion_limit` is scaled from
  `max_iterations` (each turn now spends ~3 supersteps).
- A **malformed** `payload_hex` is no longer terminal (`tool_use_malformed`
  drops out as a terminal reason): the decode error is fed back so the model can
  correct it and submit again.

`AgentState` gains `pending_validation` (propose → validate handoff) and
`validation_attempts` (telemetry). **No `RunRecord` schema change**:
`validator_output` records the last execution (the successful one on success);
the number of attempts is recoverable from `conversation.jsonl`.

## Consequences

- The apparatus now measures **iterative, feedback-driven exploitation** — build,
  run, observe, revise — which is the faithful and defensible framing of "can an
  LLM agent build a ROP chain," rather than one-shot blind generation. The 5
  replicates now measure variance across independent *iterative* sessions.
- Failures become genuine capability failures (ran out of the iteration/token/
  wall-clock budget while trying), not artifacts of a single blind shot.
- Cost/latency per run rise (multiple executions + more reasoning turns), bounded
  by the same ceilings; each execution is capped at the 30s sandbox timeout.
- The graph shape changed, so pre-/post-0014 runs are not comparable — a
  provenance note for the replication snapshot, like ADR 0010/0012/0013.
- `validate` is still the sole execution path (ADR 0002); repeating it does not
  widen the trust boundary — every execution is the same locked-down sandbox.
