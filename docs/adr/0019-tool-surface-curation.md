# ADR 0019 — Tool-surface curation: 22 tools → a curated ~8

Status: Accepted (Trial 3 — 2026-07-27)

Refines the data-driven tool layer (ADR 0011 wire format, ADR 0018 harness-injected path) and the
capability-parity boundary (ADR 0017). Changes *which* tools the agent sees and *how* the gadget
finders behave; it does not add an execution path — the validator sandbox is still the only place a
payload runs (ADR 0002/0016).

## Context

Trial 2 advertised the full 22-tool schema on every reason turn — three gadget finders (ROPgadget's
`enumerate_gadgets`, ropper's `enumerate_gadgets` + `search_gadget`), two disassembler stacks, four
pwntools helpers, five ghidra tools, plus radare2. The interim readout was unambiguous:

- **Thrash has a tool signature.** Losing runs called `enumerate_gadgets` **266×**,
  `radare2_search_pattern` 155×, `ropper_search_gadget` 153×; winners ran a tight
  recon → find → write → run → debug loop (`run_exploit_script` 109×, `radare2_disassemble_at`,
  `gdb_disassemble`). Losing = "enumerate forever"; winning = "disassemble, write a pwntools script,
  run, debug."
- **Cost is prompt, not generation** (prompt ≫ completion), and every reason turn re-billed the full
  22-tool schema, including barely-used tools (ghidra xrefs 2×, decompile 30×) with the highest schema
  weight.
- The pwntools MCP helpers (`pack_address`/`build_payload`/`generate_pattern`/`pattern_offset`) were
  redundant: under ADR 0016 the agent's `exploit.py` runs inside the sandbox where pwntools is
  installed, so it inlines `p64()`/`cyclic()` directly.

A smaller schema is a cheaper cached prefix (ADR 0023) and a cheaper cache miss, and steering the agent
toward the winning trajectory is the single biggest token/iteration lever.

## Decision

**Curate the agent surface from 22 tools to a lean ~8, as a fixed condition (not an experimental
factor), and make gadget-finding query-only.**

1. **Collapse the three gadget dumps into one query-only `find_gadget(binary, query)`.** The agent
   names the instruction shape its chosen technique needs (`"pop rdi; ret"`, `"syscall; ret"`,
   `"mov [reg], reg; ret"`); the tool compiles that to an instruction-text regex (`;` = "followed by",
   `reg` = register wildcard, case-insensitive) and returns only the matching address(es) — never a
   re-billed full dump. It is backed by the same ROPgadget engine as the retired `enumerate_gadgets`,
   and stays the injectable always-on gadget tool (`ToolLayer.find_fn`) the graph `enumerate` node
   dispatches. Choosing *which* gadgets a chain needs stays the agent's reasoning (capability-parity,
   ADR 0017); the tool only resolves a named query, exactly as `ROPgadget --binary X | grep` does
   mechanically.
2. **Add `recon(binary)`** to the radare2 server — one call returning arch/bits/endianness, checksec
   (NX/PIE/RELRO/canary), entrypoint, the function table, imports, exploitation-relevant strings
   (incl. `/bin/sh`, kept even past the string cap), and writable segments. It replaces the 5+
   round-trip `analyze + list_functions + list_imports + list_strings + search_pattern` opening
   sequence and is mechanically equivalent to `rabin2 -I` + `checksec` + `nm` + `strings` (parity).
3. **Cache the radare2 analyzed session per `(path, mtime)`.** Trial 2 re-ran the slow `aaa` on *every*
   analyze/list/disasm call; now one session is memoized per run and `aaa` runs at most once. The
   quiet-open flags (`-2`, `scr.color=0`, `scr.interactive=false`) fold in the log-hygiene fix (no
   `aaa` progress / reloc WARN / mouse-tracking escapes). `mtime` keys the cache so a rebuilt binary is
   re-opened, never stale.
4. **Drop the four pwntools agent tools** (the agent inlines them in `exploit.py`) and **retire the
   ropper gadget finders** (subsumed by `find_gadget`).
5. **Make ghidra opt-in** (registered but not in the default `ADDITIONAL_SERVERS`) — lowest Trial-2
   usage, highest schema weight — enabled per-experiment via `ToolLayer(servers=(…, "ghidra"))`.
6. **Config seam.** `ToolLayer(servers=…)` becomes a per-experiment knob driven from `experiments.yaml`
   (`tools.servers`), and per-backend limits (`limits.per_backend`) become config-driven — the
   prerequisite for the Trial-3 envelope (ADR 0024).

The curated default is: `find_gadget` + `submit_payload` + `run_exploit_script` (always on), plus
radare2 (`recon`, `disassemble_at`) and gdb (`inspect_state`, `set_breakpoint`, `disassemble`) — eight
tools. All six MCP stdio servers still exist and are launchable standalone; curation is only about what
the *agent* sees.

## Consequences

**Positive:**

- Directly attacks the measured thrash: enumerate-forever is replaced by a goal-directed query, and the
  one-call `recon` gives the agent everything the winners assembled from five round-trips.
- Smaller schema → cheaper cached prefix and cheaper cache miss every reason turn (ADR 0023); the
  radare2 session cache removes the per-call `aaa` re-analysis (the biggest single r2 speed win).
- The surface is now config-driven, so "which tools the agent has" is an auditable per-experiment
  value, and the per-backend envelope (ADR 0024) has a seam to hang on.

**Negative / limitations (recorded honestly):**

- `find_gadget`'s query language is a deliberately small regex dialect (`;`, `reg`, literal match).
  A gadget an exotic query can't express is unreachable through this tool; the agent can still write
  `exploit.py` with its own `ROP()`/gadget search. Documented, not hidden.
- Dropping ropper removes a second, differently-filtered gadget source; if ROPgadget misses a gadget
  ropper would have found, the agent loses that path. Accepted: the Trial-2 data shows the redundant
  finders drove thrash far more than they surfaced unique gadgets.
- The radare2 session cache is process-global; it assumes one binary at a time per run and is cleared
  between runs. It is lab-host-only (r2pipe absent in CI), so its memoization is unit-tested through an
  injected opener rather than a live r2.

## Alternatives considered

- **Keep all 22 tools and rely on the prompt to discourage thrash.** Rejected: Trial 2 already prompted
  toward write-run-debug, yet the losers thrashed on the dumps anyway; the schema itself is the
  re-billed cost, and prose cannot shrink it.
- **Make the tool surface an experimental factor (A/B curated vs full).** Rejected (locked decision):
  it doubles the matrix for a hypothesis the Trial-2 data already strongly supports, and the token
  budget is better spent on binaries/replicates.
- **A semantic/LLM-backed gadget finder.** Rejected: it would reintroduce hand-holding (the tool doing
  the exploit reasoning) and non-determinism; `find_gadget` resolves a query mechanically and no more.

## Ethical scope

Unchanged. Educational/CTF targets only, proof-of-concept payloads only, one sandboxed execution point
(ADR 0002/0016). This ADR removes and reshapes *analysis* tools; it grants no new capability and no new
execution surface, and the harness-injected-path confinement (ADR 0018) still applies to every
binary-analysis tool that remains.
