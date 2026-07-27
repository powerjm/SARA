# ADR 0011 — Provider-valid message wire formats and the baseline enumeration

Status: Accepted (Step 8).

Relates to ADR 0001 (LangGraph): the graph **shape** is unchanged; this changes
the *role* of one message a node emits and how backends translate the message
log. Independent of ADR 0002 / 0009.

## Context

The provider-agnostic `agent.state.Message` log mirrors the OpenAI Chat
Completions shape (`system` / `user` / `assistant` / `tool` roles, with
`tool_calls` on assistant turns and `tool_call_id` on tool turns). Each backend
translates that log to its provider's wire format.

The Step-8 tool-calling smoke exercised the premium backends against their **live
APIs for the first time** (the Step-7 cassette tests inject mocked SDK clients, so
they never validated the outgoing request). Every premium backend failed, for
reasons that shared one root cause plus per-provider gaps:

1. **Orphan baseline tool message (root cause).** `node_enumerate` seeds the run
   with a baseline `enumerate_gadgets` result **before** the agent has requested
   anything, and appended it as a `role="tool"` message with
   `tool_call_id="baseline"` — a tool result with no preceding tool call. Strict
   providers reject that: Anthropic returns `400 Unexpected role "tool"`, and the
   real OpenAI API requires a tool message to follow an assistant `tool_calls`.
   LM Studio's lenient server accepted it, which is why every local run and test
   passed while the premium path was silently invalid.
2. **Anthropic never translated tools.** `_to_anthropic_messages` passed roles
   through verbatim; Anthropic represents tool calls/results as `tool_use` /
   `tool_result` **content blocks** and requires **alternating** user/assistant
   turns.
3. **OpenAI token field.** gpt-5 (and the o-series) reject `max_tokens` and
   require `max_completion_tokens`; LM Studio only knows `max_tokens`.
4. **Gemini schema.** Gemini's function-declaration `Schema` rejects JSON-Schema
   keys it doesn't model (`additionalProperties`, `default`, `minimum`, …) with
   "Unknown field for Schema".

## Decision

**Fix the root cause at the source, and make each backend emit its provider's
valid wire format.**

- **Baseline enumeration is user context, not a tool result.** `node_enumerate`
  appends the harness-initiated baseline as a `user` message
  (`"Baseline gadget enumeration:\n…"`). Model-initiated calls remain proper
  `assistant tool_call -> tool` result pairs. This makes the message stream valid
  for every provider at once, instead of teaching each backend to special-case an
  orphan tool result.
- **Anthropic** (`_to_anthropic_messages`): assistant `tool_calls` -> `tool_use`
  blocks; `tool` messages -> a `user` turn with a `tool_result` block keyed by
  `tool_use_id`; consecutive same-role turns (e.g. the task user turn + the
  baseline user turn) merged into one turn with multiple content blocks; `system`
  omitted when absent.
- **OpenAI** (`_max_output_param`): the base `OpenAIBackend` sends
  `max_completion_tokens`; `LMStudioBackend` overrides back to `max_tokens`.
- **Gemini** (`_sanitize_schema`): recursively drop schema keys outside a
  supported whitelist; `_to_gemini_contents` merges consecutive same-role turns
  and folds `system` into the leading user turn (tool results are already
  rendered as user text, so Gemini needs no structured pairing).

## Consequences

- The premium arm can run for record. The cassette tests remain (response
  decoding), and new unit tests cover the translation *inputs* the mocked clients
  never checked (`test_provider_backends.py`).
- The trace/message log changes shape: the baseline enumeration is now a `user`
  message, not a `tool` message (one integration assertion updated). No
  `RunRecord` schema change, so no `schema_version` bump.
- Gemini loses non-structural schema hints (`minimum`/`default`/…); the model
  still gets types, descriptions, and `required`, and the tool layer validates
  arguments regardless.
- Live verification against the real APIs is required before a run for record —
  the mocked-client tests cannot catch a provider contract change (this ADR is
  the direct consequence of that gap).
