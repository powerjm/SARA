# ADR 0015 — Bound the agent by real budgets; never force a tool call

Status: Accepted (Step 8). **Supersedes ADR 0012** (retry-nudge / give-up).

Relates to ADR 0014 (iterative validation) — which this completes — and ADR 0001
(LangGraph): a no-tool-call turn now self-loops `reason -> reason` unconditionally
instead of giving up.

## Context

Two mechanisms bounded a run, both artifacts of the old one-shot world:

1. **`max_iterations`** — a cap on the *count* of reason turns. This is an
   artificial proxy: an agent that thinks in many small turns is cut off sooner
   than one that thinks in a few large turns, though they cost the same. It has
   nothing to do with the real resource (tokens / time).
2. **The ADR 0012 nudge/give-up** — a no-tool-call turn was prodded to "call a
   tool," and after `max_nudges` prods the run was *abandoned* (`agent_gave_up`).

Under iterative validation (ADR 0014) both are actively harmful. A capable model
reasoning its way through an `execve("/bin/sh")` chain — enumerating the exact
gadgets it needs, working out register side-effects — is *making progress*, but
`max_iterations` counts it down and the nudge machinery abandons it before it
finishes, even with plenty of token/time budget left. The harness ends up
measuring turn-count and tool-call eagerness, not capability. The agent also had
**no visibility into its budget**, so it could not pace itself.

## Decision

**Bound each run by the real limits — token budget and wall-clock time — and tell
the agent what they are. Never force a tool call and never give up early.**

- `node_reason` terminates (`budget`) only on the token budget or wall-clock cap.
  `max_iterations` is kept **only as a high runaway backstop** (default 100) so a
  pathological loop ends cleanly rather than hitting the LangGraph recursion cap;
  it is set well above what any real run reaches, so tokens/time bind first.
- **The agent is told its budget.** `node_ingest` states the token (and, if set,
  wall-clock) budget for the run; after a no-tool-call turn the continuation
  message reports the *remaining* budget, so the model can pace itself.
- **A no-tool-call turn is not a give-up** (superseding ADR 0012). `route_after_
  reason` always returns `"reason"`; `node_reason` appends a non-coercive
  continuation ("Continue. You can keep reasoning… or call a tool when ready. You
  do not have to act yet. Budget: …"). The run ends only on success, the real
  budget, a refusal, or truncation. `max_nudges` is now inert (kept so old
  configs / `RUN_MAX_NUDGES` do not error).

The **token budget and wall-clock cap are the experimenter's knobs** in
`experiments.yaml` (`limits.tokens`, `limits.wall_clock_seconds`) — sized per the
run, small enough for premium models to stay under their USD caps, large enough
to give slow local models room. No `RunRecord` schema change.

## Consequences

- The apparatus measures capability under a real resource budget, not a turn
  count, and stops abandoning agents mid-progress. This is the point of ADR 0014.
- **Failed runs now consume close to their full budget** (the agent reasons until
  it succeeds or runs out) instead of bailing early. That raises cost/latency per
  failed run — deliberately traded for not cutting the agent off. For premium
  models the per-backend USD cap is the real spend guard, so the token budget must
  be sized with that in mind (a too-large token budget means fewer cells complete
  before the dollar cap halts the backend).
- `agent_gave_up` becomes effectively unreachable; nearly all non-success
  outcomes are now `budget_exhausted`. The classifier still maps it to
  FAILURE/OTHER for any legacy records.
- Pre-/post-0015 runs are not comparable — a provenance note for the replication
  snapshot, like ADR 0010/0012/0013/0014.
