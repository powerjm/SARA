# ADR 0022 — Context engineering: send-time compaction + a within-run store

Status: Accepted (Trial 3 — 2026-07-27)

Attacks the prompt≫completion cost explosion (the single largest structural token sink identified in
Trial 2) without changing the graph shape (ADR 0001 replay) or the wire-format contract (ADR 0011).
Pairs with ADR 0023 (prompt caching); the two are designed together (the caching-vs-compaction
synthesis below).

## Context

Trial 2's root cause was verified in the code: `node_reason` sent `_to_backend_messages(state.messages)`
— the *whole accumulated log* — every REASON turn, and `state.messages` only ever grows (append at
ingest, every tool result, every assistant/validation turn). A 30-iteration run therefore re-billed all
30 iterations of tool output on turn 30. Cost was prompt-dominated (e.g. `qwen3-coder`'s completion
median was ~1k tokens against a ~468k prompt median); the sink was **re-sending large tool outputs
every turn**, not model verbosity.

The plan proposed migrating `AgentState.messages` to LangGraph reducer channels (`add_messages` /
`RemoveMessage`). That is a large, high-risk rewrite of a high-review-cost subsystem (the graph), and
LangGraph reducers that trim history can orphan a `tool_use` from its `tool_result` and trip
strict-provider 400s (ADR 0011).

## Decision

**Compact at send time, not in state.** The token win is entirely about what is *sent* to the backend,
so that is the only thing changed:

1. **`state.messages` stays the full append-only log.** The trace, the stored `conversation.jsonl`, and
   LangGraph replay are all byte-for-byte unaffected — the graph shape and ADR 0001's replay guarantee
   are preserved. This is the key move that makes the whole change low-risk.
2. **`_build_backend_messages(state, config)`** shapes the wire payload. Short runs (≤
   `compact_after_iterations` assistant rounds, default 8) send the full log unchanged. Past that, the
   send is a **stable prefix** — system + the original task + the pinned C1 plan + a deterministic
   "established facts" digest — followed by the last `keep_recent_messages` turns verbatim.
3. **L8.1 externalize → digest.** Full tool outputs live in `state.observations` / the trace; the
   compacted send carries only a terse one-line `_digest` per result. (Trial-3 tools are already terse
   — `find_gadget` is query-only, `recon` is a one-call snapshot, ADR 0019 — so a separate on-demand
   `recall` tool was judged unnecessary and *not* added: it would put a tool back on the curated
   surface for a need the digest + terse tools already cover. Recorded as a deliberate scope choice.)
4. **L8.2 deterministic compaction.** The facts block is **code-built** (`_established_facts`), a pure
   function of `state` — no LLM summarizer — so a replay reproduces it exactly (reproducibility over a
   marginally tighter summary).
5. **L8.3 superseding.** The digest keeps only the **latest** observation per `(tool, args)`, so the
   repeated enumerate/search thrash that dominated Trial-2 failures collapses to one line.
6. **C1 planning-commit.** The agent's first substantive reasoning turn is captured once into the
   run-scoped store (`state.scratchpad["plan"]`) and pinned into the stable prefix, so the plan survives
   compaction and steers every later turn. Parity: the agent authors its own plan; the harness only pins
   it.
7. **Within-run store.** `state.scratchpad` is a per-run dict; a fresh state starts empty, so no
   plan/facts leak across runs or threads — preserving the independence the paired stats (McNemar /
   Friedman) assume (Trial 3 §1).

**Wire-format integrity (ADR 0011).** The compacted history is rendered as plain user text — never
dangling `tool_use`/`tool_result` blocks — and the verbatim tail is cut at a **clean turn boundary**:
any leading orphaned `tool` result (whose `tool_use` fell before the cut) is dropped, so a strict
provider never sees an orphaned pair. Tested directly.

**Caching-vs-compaction synthesis (with ADR 0023).** Caching rewards an append-only stable prefix;
compaction rewrites early messages and would invalidate the cache from the edit point. The resolution:
keep the prefix (system + task + pinned plan) **stable**, confine all churn to the suffix, and let the
facts digest change only in batches — so the cache-miss reset is rare while the re-billed log still
shrinks every turn.

## Consequences

**Positive:**

- Directly removes the prompt-explosion: a long run no longer re-bills its whole history — the middle
  collapses to a superseded-deduped digest, and only the recent tail is verbatim.
- Zero graph-shape change and zero state-schema change: `state.messages` is untouched, so trace/replay
  and every existing test's notion of the log still hold; short runs are byte-identical to before.
- Deterministic (no LLM summarizer) → reproducible, the overriding value for a research instrument.

**Negative / limitations (recorded honestly):**

- The digest is lossy by construction: a full tool output past the recent window is only summarized. For
  Trial-3's terse tools this is minor, but a detail the model needed and did not carry into its own
  reasoning could be lost. No `recall` escape hatch is provided (scope choice above).
- C1 captures the *first* reasoning turn as the plan; if the agent's real plan crystallizes later, the
  pinned text is its opening thoughts, not its final strategy. Accepted as a cheap, parity-preserving
  realization that needs no extra model call or graph node.
- Compaction is send-time only, so the model's *own* prior long outputs (assistant text) in the tail are
  still sent verbatim within the recent window; the win is on tool results and the compacted middle.

## Alternatives considered

- **Full LangGraph reducer-channel migration (`add_messages`/`RemoveMessage`).** Rejected: high-risk
  rewrite of the graph for no additional observable benefit over send-time compaction, and the trimming
  reducers are exactly what orphans tool pairs. Send-time compaction achieves the same token reduction
  with the wire-format guarantee intact and the replay guarantee untouched.
- **An LLM summarizer for the compacted middle.** Rejected: non-deterministic and itself token-costly;
  a research instrument prizes a reproducible, code-built digest over a marginally tighter prose summary.
- **A `recall(key)` tool over a keyed store.** Deferred: the terse Trial-3 tools + the digest already
  keep the salient facts in-context; adding a tool re-widens the curated surface (ADR 0019) for a need
  not yet demonstrated. Revisit if a readout shows the digest dropping needed detail.

## Ethical scope

Unchanged. Educational/CTF targets only, proof-of-concept payloads only, one sandboxed execution point
(ADR 0002/0016). This ADR only reshapes the in-context prompt within a single run; it adds no
capability, no execution path, and no cross-run state.
