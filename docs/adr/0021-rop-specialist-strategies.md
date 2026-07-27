# ADR 0021 — ROP-specialist prompting strategies

Status: Accepted (Trial 3 — 2026-07-27)

Replaces the generic prompting arms for the Trial-3 matrix with two ROP-specialist arms that share one
goal, one curated toolset (ADR 0019), and one expert methodology fragment, differing only in reasoning
scaffold. Stays within the capability-parity boundary (ADR 0017) and the single success definition
(ADR 0009); discloses the 100-pt rubric (ADR 0020).

## Context

Trial 2's strategy factor was the generic `zero_shot` / `chain_of_thought` / `react` triad — reasoning
styles borrowed from the prompting literature, none of them about ROP. The interim readout showed the
signal was not "which generic reasoning style" but "did the agent operationalize the tools": winners
reached `run_exploit_script` by ~iteration 8; losers looped on gadget enumeration (`enumerate_gadgets`
185×) and died at the token cap. The generic arms did nothing to encode the *methodology* of building a
ROP chain, so they mostly measured incidental style differences on top of a shared failure mode.

Trial 3 wants the strategy factor to test something ROP-specific and actionable, while keeping the
comparison clean (arms equal in everything but the one thing under test).

## Decision

**Replace the generic arms in the matrix with two ROP-specialist arms — `template_backward` and
`recon_first` — that are identical except for their reasoning scaffold.**

1. **A shared expert fragment, byte-identical across both arms** (`_with_trial3_expert`):
   - **Success criterion + iterate loop** (as every strategy already gets, ADR 0009/0014).
   - **Expert methodology** (Mechanism 1 / L7): a decision procedure that NAMES the steps and named
     techniques — ret2syscall, move-chain, arithmetic byte-synthesis, two-stage `.bss` pivot, `ret N`
     realign — so a model can recognize which sub-problem it faces, **without any target's answer**.
     It is pwn-textbook altitude (`checksec` → NX/PIE/static implications, `cyclic` for the offset, the
     execve shape, the three-way "get /bin/sh into memory" decision), never this binary's offset,
     address, or chain (capability-parity, ADR 0017).
   - **The 100-pt rubric at face value** (ADR 0020), including the deliberately-unwinnable root bonus,
     disclosed as attainable.
   - **The trailing-stdin marker idiom**: how to satisfy the anti-echo guard and feed bonus commands to
     the spawned shell, since the validator runs `target < payload`.
2. **Two reasoning scaffolds, the only thing that differs:**
   - **`template_backward`** — start from the execve north-star, turn it into a short shopping list of
     the specific gadgets it needs, and resolve them with narrow `find_gadget` queries. Counters
     enumerate-forever by making enumeration goal-directed.
   - **`recon_first`** — walk the decision procedure top-down: `recon` the target, classify which
     sub-problem it is on the graded ladder, then hunt only the gadgets that classification needs.
3. **The generic arms (`zero_shot`/`chain_of_thought`/`react`/`majorca`) are retired from the Trial-3
   matrix but kept in the registry and the `PromptingStrategy` enum**, so Trial-1/2 records still load
   and the arms remain runnable ad hoc. Adding the two new enum values is additive (like MAJORCA), not
   a `schema_version` event.
4. **Terse framing (L0)** throughout, since the system prompt is re-billed every reason turn (ADR 0022
   compaction keeps it in the stable, cached prefix — ADR 0023).

## Consequences

**Positive:**

- The strategy factor now tests a real, ROP-specific hypothesis (backward-from-goal vs.
  recon-then-classify) instead of incidental reasoning style, on top of a methodology both arms share —
  so a difference is attributable to the scaffold, not to one arm knowing more.
- The shared fragment is a fixed condition enforced in code and by test, so the arms cannot silently
  diverge in goal knowledge, rubric, or toolset — only in scaffold.
- Encoding the methodology directly attacks the Trial-2 failure mode (enumerate-forever) without
  hand-holding: it names techniques, never answers.

**Negative / limitations (recorded honestly):**

- Teaching the methodology narrows the gap between a strong and a weak model on *knowing what to do*,
  so the arm may compress variance that Trial 2 saw; that is the intended trade (measure execution, not
  whether the model has read a pwn course), stated in threats-to-validity.
- Two arms is a smaller strategy factor than Trial 2's three; the generic-vs-specialist question is not
  re-litigated here (the Trial-2 data already motivates the switch).
- The methodology fragment is at textbook altitude but is still *guidance*; where exactly "general
  craft" ends and "this target's answer" begins is a judgment call — kept on the general side (no
  offsets/addresses/chains) and called out in threats-to-validity.

## Alternatives considered

- **Keep the generic arms and add the specialists (five-arm matrix).** Rejected: it doubles the
  strategy factor and the token budget for a comparison Trial 2 already resolved (generic style is not
  the signal).
- **One specialist arm.** Rejected: a single arm has nothing to compare against; the two scaffolds are
  the experiment.
- **Put the expert methodology in the shared success criterion for ALL arms.** Rejected: it would
  change the retired generic arms and break comparability with Trial-1/2 records; the methodology is a
  Trial-3 specialist-arm addition, scoped to the two new arms.

## Ethical scope

Unchanged. Educational/CTF targets only, proof-of-concept payloads only, one sandboxed execution point
(ADR 0002/0016). The prompts teach general exploit-dev craft at textbook altitude and disclose the
scoring oracle; they solve no specific target and grant no new capability or execution surface.
