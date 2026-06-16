# ADR 0003 — Chain fingerprint is the ordered gadget-address sequence

Status: Accepted (Step 3)

## Context

The validator must distinguish a `KNOWN_REDISCOVERY` (the agent reproduced the
documented exploit chain) from a `NEW_DISCOVERY` (the agent found a *different*
working chain). Both are successful runs — return code 0 with the success
marker on stdout — so success alone cannot tell them apart. We need a cheap,
stable identifier for "which chain is this" that we can compute for the
documented exploit once and compare against whatever the agent submits.

A **chain** here is the ordered sequence of control-flow targets the payload
hands to the CPU: the gadget addresses plus the final target address. It is
*not* the raw payload bytes (those also contain padding and data operands such
as the `0xdeadbeef` magic value, which are incidental to "which gadgets, in
what order"). For `sample_overflow` the documented chain is exactly
`chain.json`'s `documented_gadget_addresses`:
`[0x4011ad, 0x4011ae, 0x401166]` (`pop rdi ; ret`, the alignment `ret`, `win`).

The open question (flagged on Step 3 of `docs/SARA_DEVELOPMENT_HISTORY.md`): do we
fingerprint the **sorted** address set (robust to reordering) or the **ordered**
sequence (order-sensitive)?

## Decision

The chain fingerprint is the **SHA-256 of the ordered gadget-address sequence**.
Order is significant; the sequence is **not** sorted before hashing.

Canonical encoding (so the digest is reproducible across hosts and Python
builds), implemented by `validator.runner.chain_fingerprint`:

1. Each address is formatted as a zero-padded 16-digit lowercase hex string
   (64-bit, e.g. `00000000004011ad`).
2. The encoded addresses are joined in order with a single comma `,`.
3. The fingerprint is `sha256(encoding.encode("ascii")).hexdigest()`.

`chain_fingerprint` is defined in exactly one place. The harness uses it to
fingerprint the documented chain (from `chain.json`'s
`documented_gadget_addresses`) and the validator uses it to fingerprint the
candidate chain the `PROPOSE` node committed to. `validator.runner.execute`
sets `matched_documented_chain=True` iff a `documented_chain_fingerprint` was
supplied **and** the candidate chain's fingerprint equals it.

## Consequences

**Positive:**

- **Stricter, and that is the point.** Reordering gadgets generally changes what
  a chain does; treating `[A, B, C]` and `[C, B, A]` as the same chain would be
  wrong. "Same gadgets, different order" is reported as a `NEW_DISCOVERY`, which
  is the honest classification for the thesis — a distinct, separately-working
  chain.
- One canonical definition shared by the documented side and the candidate side,
  so the comparison cannot drift.
- Cheap and deterministic: no binary re-analysis, no dependence on ROPgadget
  output ordering.

**Negative:**

- A chain that is genuinely equivalent up to a benign reordering (e.g. two
  independent `pop` gadgets whose order does not matter) fingerprints
  differently and is logged as a `NEW_DISCOVERY`. We accept this: it
  over-counts new discoveries rather than silently collapsing distinct chains
  into a rediscovery, and the qualitative trace still records the gadgets, so an
  analyst can recognise the equivalence by hand at coding time.
- The candidate fingerprint is computed from the ordered addresses the proposer
  *reports*, not recovered from the executed bytes. This is sound because the
  proposer builds the payload **from** those addresses, and — per ADR 0002 — the
  success decision itself still comes only from real execution (return code +
  marker). The fingerprint only sub-classifies an already-successful run into
  known vs new.

## Alternatives considered

- **SHA-256 of the sorted address set** — rejected. It is robust to reordering,
  but that robustness erases a real distinction: a reordered chain is a
  different program. It would mislabel genuinely new chains as rediscoveries and
  understate the new-discovery rate the thesis reports.
- **Hash of the full payload bytes** — rejected. Padding length and data
  operands (e.g. the magic value) would make trivially-different payloads that
  drive the *same* chain fingerprint differently, the opposite failure: it would
  understate rediscoveries.
