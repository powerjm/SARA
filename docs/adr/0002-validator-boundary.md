# ADR 0002 — Validator owns all payload execution

Status: Accepted (Phase 0)

## Context

The agent has tools that *could* execute candidate payloads (GDB has a `run` command, pwntools can spawn processes). If those execution paths existed inside the tool layer, every backend would have a chance to exploit something subtly different — different timeout policies, different seccomp profiles, different output capture — and the "did this exploit work?" decision would be entangled with the agent's own claims.

## Decision

The validator is the **only** component that executes candidate payloads. GDB is exposed to the agent in inspect-only mode (`run_with_payload` is internal to the validator, never reachable from a tool the agent calls).

## Consequences

**Positive:**

- One sandbox policy across every run, regardless of backend.
- The success/failure decision is made by a single component, not by the agent's interpretation of return codes.
- Adding a new tool cannot introduce a new execution path.

**Negative:**

- Agent cannot do speculative execution (e.g., "try this chain quickly and see what happens") inside a reasoning step. It must commit to a payload and submit it to the validator. Believed to be a feature, not a bug: it forces the agent to articulate its hypothesis before testing it.

## Alternatives considered

- **GDB-run as a tool, with a wrapped sandbox** rejected because the wrapping logic would have to be re-implemented for every other
  potentially-executing tool. Validator boundary keeps the policy in one place.
