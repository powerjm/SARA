# ADR 0024 — Per-backend envelope + `n_ctx_loaded` telemetry

Status: Accepted (Trial 3 — 2026-07-27)

Makes the per-run resource envelope a **per-backend** config (the config-loader seam deferred from
Trial 2 §4/D7, built in ADR 0019) and adds the `n_ctx_loaded` per-run telemetry that closes a Trial-2
confound. Consumes the schema-v6 field added in Phase A.

## Context

Trial 2 applied one global envelope (token cap + wall-clock) to every backend. Two problems surfaced in
the readout:

- **The small free locals burned the most tokens for near-zero success** (`gpt-oss-20b` ~468k prompt
  median; `whiterabbitneo` ~505k / 45 iters). They cost nothing in dollars, so a bigger wall-clock is
  free — but the premium models must stay bounded by dollars, so a single global clock can't serve both.
- **A context-window confound was invisible.** `qwen3-*` should load at 256k but *sometimes* loaded far
  lower — a non-reproducible LM Studio loading inconsistency that drove `qwen3-30b-abliterated`'s
  ADR-0013 `truncated` cap in 4/6 runs. Nothing on the record showed the context a run actually had, so
  "couldn't do it" and "loaded a crippled context and truncated" were indistinguishable after the fact.

## Decision

**1. Per-backend envelope, config-driven.** `experiments.yaml` gains `limits.per_backend`: a mapping of
backend handle → partial `{tokens, wall_clock_seconds, n_ctx}`. `BatchConfig.settings_for(backend)`
overlays a backend's envelope on the global `limits`, so the free locals get a bigger wall-clock (~1200s
in the Trial-3 matrix) while the premium models keep the global budget and stay bounded by
`usd_per_backend`. This uses the config seam from ADR 0019 (the tool-surface knob and the per-backend
limits were built together).

**2. `n_ctx_loaded` per-run telemetry (schema v6).** The LM Studio backend reports the context its local
server actually loaded (native `GET /api/v0/models`, defensively — a probe failure yields `None`, never
aborts a run); premium/hosted backends leave it `None`. `build_run_record` stamps it onto every
`RunRecord`, and `aggregate.py` surfaces the per-cell value, so a silent under-load is visible in the
data instead of inferred from a truncation cap.

**3. `n_ctx` is a documented launch gate, not a harness action.** The harness cannot set LM Studio's
loaded context — that is an LM Studio server/model configuration. So `per_backend.<model>.n_ctx` records
the context each model **must be pinned to**, and the preflight gate asserts, per run, that
`n_ctx_loaded >= 32768` (and matches the pin). The pins in the Trial-3 matrix: `gpt-oss-20b` 32768,
`qwen3-30b-abliterated` 262144 (pinned high precisely to defeat the Trial-2 under-load),
`whiterabbitneo-v3-7b` 32768 (a hard model ceiling — viable only because L8 context engineering ships
this trial, ADR 0022).

**4. Throughput gate, not just budget.** A model is dropped or re-hosted if its measured tok/s cannot
finish a trajectory within the cap — no wall-clock rescues 3.5 tok/s. `qwen3-coder-30b` is dropped on
this basis (Trial-3 roster). This is an operator checklist item (measured on the lab host), enumerated
in `make preflight`.

## Consequences

**Positive:**

- The envelope fits each backend: free locals get the clock they need, premium models stay dollar-
  bounded, on one config with no env-var juggling.
- The context a run actually had is now on the record, so the Trial-2 loading confound is diagnosable
  (and, reconciled with the max-output cap, an ADR-0013 truncation loop from a crippled context can be
  attributed rather than mistaken for incapacity).
- The throughput gate keeps a physically-cannot-finish arm out of the matrix by construction.

**Negative / limitations (recorded honestly):**

- `n_ctx` in the config is advisory to the operator, not enforced by the harness — a mispinned LM Studio
  model is caught only by the preflight per-run assertion, not prevented. The record makes the miss
  visible; it does not stop it.
- `n_ctx_loaded` depends on LM Studio's native REST endpoint; a server that does not expose it reports
  `None` (a telemetry gap, not zero context) — readers must treat `None` as "unreported", not "crippled".
- The tok/s gate is a manual lab-host measurement, not an automated check — it cannot be verified off
  the host.

## Alternatives considered

- **One global envelope with a generous clock for everyone.** Rejected: it either under-serves the free
  locals (too short) or lets premium models run long enough to blow the dollar cap before it binds; the
  two need different envelopes.
- **Infer the loaded context from truncation behaviour.** Rejected: that is exactly the Trial-2 ambiguity
  — a truncation cap conflates a crippled context with genuine incapacity. Recording the loaded context
  removes the guess.
- **Have the harness set LM Studio's n_ctx via the API.** Rejected: LM Studio loads a model with a
  context at load time; the harness talks to an already-loaded server and does not own its load
  configuration. Pinning is an operator step; the harness verifies it after the fact.

## Ethical scope

Unchanged. Educational/CTF targets only, proof-of-concept payloads only, one sandboxed execution point
(ADR 0002/0016). This ADR changes only resource budgeting and adds a telemetry field; it grants no new
capability and no new execution surface.
