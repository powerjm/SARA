# ADR 0010 — Parse text-format `Action:` tool calls from reasoning strategies

Status: Accepted (Step 8).

Relates to ADR 0001 (LangGraph, inspectable/replayable control flow): the graph
**shape** is unchanged — this adds a parsing step inside `node_reason`, not a new
node or edge. Independent of ADR 0002 (validator boundary) and ADR 0009 (success
marker).

## Context

The agent graph (`agent/graph.py`) dispatches only **native, structured** tool
calls: `route_after_reason`, `node_enumerate`, and `_find_submit_call` all read
`message.tool_calls` (the provider's function-call objects). A reason turn that
carries no native tool call and no committed payload routes straight to
`propose → validate`, terminating as `agent_gave_up`.

Two of the four prompting strategies — `react` and `chain_of_thought` — are
independent variables in the experiment, and both instruct the model to emit its
action as **text** in the reasoning transcript:

- react: `Thought: … / Action: enumerate_gadgets(…) / Observation: …`
- chain_of_thought: `THOUGHT: … / ACTION: submit_payload(…)`

A model that follows the prompt faithfully therefore writes its action as prose,
which the graph ignored — the run gave up on turn one despite the model correctly
intending a call. This was found by the Step-8 tool-calling smoke: `qwen2.5-coder-7b`
under `react` emitted `Action: enumerate_gadgets({…})` **as text** and was scored
`failure / other`, while the same model's native-tool-calling siblings proceeded.
Left unfixed, `react`/`chain_of_thought` would be measured as systematically worse
not because the reasoning style is worse but because the harness could not read
their actions — a confound that invalidates the strategy comparison.

Two remedies were considered:

- **(a)** Rewrite the `react`/`chain_of_thought` guidance so the model keeps the
  Thought/Action *reasoning* but issues the action as a native tool call.
- **(b)** Teach the harness to parse the text-format `Action:` line into a tool
  call, honoring the strategies' literal ReAct/CoT contract.

## Decision

**Adopt (b).** When a reason turn produces **no** native tool call, the harness
parses `Action:` / `ACTION:` lines for the known tools and treats them as calls.

- `agent.tools.parse_text_actions(text)` returns native-shaped call dicts
  (`{"id", "name", "arguments"}`) so everything downstream is unchanged. It is a
  pure, unit-tested function (mirroring the MCP-server split: parsing logic sits
  behind a plain callable). Argument blobs are decoded as JSON (`raw_decode`, so
  trailing prose is tolerated); extraction is quote- and nesting-aware so a paren
  inside a string does not close the group early.
- `node_reason` wires it in as a **fallback only**: `response.tool_calls or
  parse_text_actions(response.text)`. **Native tool calls always win**, so
  strong tool-callers (which emit native calls even under a ReAct prompt) are
  unaffected, and the change is a strict superset of the prior behavior.
- Recognition is limited to the two known tools (`enumerate_gadgets`,
  `submit_payload`) and anchored on `\baction\s*:` immediately followed by
  `name(`, so a prose mention of a tool — or a word like "reaction:" — does not
  trigger a spurious call (in particular, never a spurious terminal
  `submit_payload`).

Rejected (a) because rewriting the strategy prompts changes what `react` /
`chain_of_thought` *are* as independent variables; (b) keeps each strategy's
published contract intact and moves the fix into the apparatus.

## Consequences

- `react` / `chain_of_thought` runs now progress on models that emit text
  actions, and such a text action loops back through `enumerate` for further
  rounds — which also softens (but does not remove) the one-shot give-up on the
  *first* reason turn. A model that emits pure prose with **no** `Action:` line
  (possible under `zero_shot` / `majorca`) still terminates as `agent_gave_up`;
  whether to add a "no tool call detected — re-ask" nudge is deliberately left
  open (it would touch the graph shape and needs its own ADR).
- The parser is heuristic and intentionally narrow: JSON-object arguments only,
  known tools only. An unparseable blob yields empty arguments, which the tool
  layer reports back to the agent as a normal tool error rather than crashing.
- No schema change: `RunRecord` and outcomes are untouched, so no
  `schema_version` bump. Outcome *distributions* for the two reasoning strategies
  will shift (fewer spurious `agent_gave_up`); runs recorded before this change
  are not comparable to runs after it for those two strategies — a provenance
  note for the replication snapshot.
