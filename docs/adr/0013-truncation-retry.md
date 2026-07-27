# ADR 0013 — Recover from a reply cut off at the output-token cap

Status: Accepted (Step 8).

Relates to ADR 0001 (LangGraph — no new node or edge; the retry is internal to
`node_reason`), ADR 0011 (backend wire-format contract — this reads the same
provider stop/finish reason `detect_refusal` uses), and ADR 0012 (retry-nudge —
a sibling bounded-retry for a *different* failure: no-tool-call vs cut-off call).

## Context

`node_reason` calls `backend.chat(..., max_tokens=max_tokens_per_call)` and hands
the reply straight on. `route_after_reason` then routes a `submit_payload` tool
call to `propose`, which reads `payload_hex` out of the call's `input`.

The per-call cap was **4096**. The first live premium run for record
(`claude-sonnet / cgc-cadet-00001 / zero_shot`) exposed the failure this creates:
the model reasoned out a correct CGC `_terminate` chain, then on its final turn
generated **exactly 4096 completion tokens** and its `submit_payload` call came
back with **empty `input {}`** — the reply was cut off (`stop_reason ==
"max_tokens"`) while the tool-call JSON was still being written. `propose` found
no `payload_hex`, `bytes.fromhex(...)` raised, and the run was recorded as
`FailureMode.TOOL_USE_MALFORMED`.

Nothing in the loop inspected the stop reason: `node_reason` only ran
`detect_refusal` (which looks for `stop_reason == "refusal"`), so a `max_tokens`
stop passed through silently. The result **misattributes a harness limitation to
the model**: it measures the 4096-token budget, not whether the model can build a
ROP chain. The bias is worst exactly where it matters most — verbose native
tool-callers (Claude Sonnet/Opus), the gpt-5 reasoning model (hidden reasoning
tokens), and the reasoning-heavy strategies (chain_of_thought / react / majorca)
— i.e. the most expensive cells of the run for record.

## Decision

**Detect a cut-off reply and recover, rather than letting the broken tool call
become a spurious failure. Two parts:**

1. **Raise the per-call output cap** `AgentConfig.max_tokens_per_call`
   **4096 → 16384**, surfaced through `RunSettings.max_tokens_per_call` /
   `RUN_MAX_TOKENS_PER_CALL`. This alone removes almost all truncation on these
   small binaries; premium spend stays bounded by the per-backend USD caps in
   `experiments.yaml`.

2. **Detect + bounded retry.** A new `Backend.detect_truncation(response)` reads
   the provider stop/finish reason from `response.raw` (Anthropic `max_tokens`,
   OpenAI-family `length`, Gemini `…MAX_TOKENS`; substring/case-insensitive).
   When a reason turn is truncated, `node_reason` discards the unusable
   (half-written) tool call, appends a concise-reply re-prompt as a `user` turn,
   and calls again — up to `config.max_truncation_retries` times (default **2**,
   `RUN_MAX_TRUNCATION_RETRIES`). The retry loop lives **inside** `node_reason`
   (`_chat_with_truncation_retry`), so the graph shape is unchanged (ADR 0001).

If every attempt is still cut off, the run ends with `termination_reason ==
"truncated"` → `Outcome.FAILURE, FailureMode.OTHER`. `OTHER` (not
`TOOL_USE_MALFORMED`, not `BUDGET_EXHAUSTED`) keeps `TOOL_USE_MALFORMED` reserved
for a genuinely malformed submission made *within* budget, and keeps
`BUDGET_EXHAUSTED` for the run-level token/iteration/wall-clock caps; the exact
cause stays visible in the trace's `termination_reason`. **No `RunRecord` schema
change** (no new `FailureMode`), matching the ADR 0010/0012 precedent.

Token and cost from *every* attempt (including truncated ones) are accumulated
into the run — a truncated attempt is still billed. Truncation retries do **not**
add committed assistant turns, so they do not consume the `max_iterations`
reasoning-round budget or the `max_nudges` budget; they are bounded solely by
`max_truncation_retries`.

## Consequences

- The premium arm and the reasoning strategies are measured on capability, not on
  a 4096-token clip. The run for record could not be trusted without this.
- Cost/latency per run rise: bigger completions, and a truncated turn costs one
  or more extra calls. Bounded by `max_truncation_retries` (≤ 2 extra calls per
  reason turn, each ≤ 16k tokens) and, for premium, by the USD caps. The
  run-level token budget is still only checked on `node_reason` entry, so an
  in-progress retry burst can overshoot it by at most `max_truncation_retries ×
  max_tokens_per_call`; negligible against the 500k per-run budget.
- Outcome distributions shift (fewer `TOOL_USE_MALFORMED`); like ADR 0010/0012,
  pre-/post-change runs are not directly comparable — a provenance note for the
  replication snapshot.
- `detect_truncation` is metadata-only (no keyword fallback): a backend whose
  `raw` omits the stop reason simply never triggers the retry (it degrades to the
  raised cap alone). All four run-for-record providers surface it (ADR 0011).
- Both knobs default conservatively. `max_truncation_retries = 0` still *detects*
  a cut-off reply and ends the run as `truncated` (no mislabel) — it only skips
  the re-prompt; it does not restore the pre-0013 "use the broken call as-is"
  behavior, which is intentional (the mislabel was the bug).
