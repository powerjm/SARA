# ADR 0018 — The harness injects the target path into analysis tools; the model never supplies it

Status: Accepted (Trial 2 — 2026-07-26)

Refines ADR 0017 (no baseline enumeration — the agent analyzes the target itself) and sits under the
one-execution-point rule (ADR 0002/0016). Does not change the graph shape or any execution policy.

## Context

The binary-analysis tools (ropgadget, radare2, ropper, gdb, ghidra) each take a `binary_path`
argument. Until now that value came straight from the **model**: the ToolLayer passed the model's
tool-call arguments through to the tool function verbatim.

That was harmless while ADR 0011's baseline gadget dump existed — `node_enumerate` auto-ran
`enumerate_gadgets` with the *correct* host path, so the agent got gadgets without ever having to name
a path itself. ADR 0017 removed that baseline: the agent must now decide to analyze the target and
call the tools itself. But the only path the agent is ever told about is `/work/target`, stated in the
`run_exploit_script` contract (ADR 0016) — and that path exists **only inside the validator's Docker
sandbox** (`validator/runner.py::_stage_workdir` copies the target there as `/work/target`). The
analysis tools do **not** run in that sandbox; they run in the harness process on the host, where
`/work/target` is not a file.

The result, seen in the very first Trial-2 shakeout run
(`runs/e1e2b4a4-.../conversation.jsonl`): every `radare2_*` / `ghidra_*` call the model made returned
`FileNotFoundError: binary not found: /work/target`, because the model dutifully passed the only path
it knew and the host tools could not see it. The agent fell back to `objdump`/`nm` via
`run_exploit_script` and burned its entire 200k-token budget on raw dumps before it could build a
chain — a **confounded** failure (tool-plumbing, not capability), the same class as the Trial-1
confound.

There is also a latent integrity problem in the old design independent of the path mismatch: because
the model chose `binary_path`, it could point a host-side tool (e.g. `ghidra_list_strings`) at **any**
readable host file. The harness, not the agent, should decide which file the tools analyze.

## Decision

**The harness owns `binary_path`. The model neither supplies it nor sees it.**

1. **Inject at dispatch time.** `ToolLayer.dispatch(name, arguments, *, binary_path)` now takes the
   run's staged host path (threaded from `state.binary.binary_path` in `node_enumerate`) and forces it
   into the arguments of every tool whose schema declares `binary_path`, overriding any model-supplied
   value (`_inject_binary_path`). This is the *same* file the validator copies into the sandbox as
   `/work/target`, so the analysis tools (host) and `run_exploit_script` (sandbox) operate on
   identical bytes by two names. Tools with no `binary_path` input (the pure pwntools helpers —
   `pack_address`, `build_payload`, …) are passed through untouched.

2. **Strip it from the advertised schema.** `specs()` removes `binary_path` from the model-facing copy
   of each analysis tool's schema (`_advertised_schema`), so the model is never asked for a path it
   cannot know and whose value the harness would discard. The server-owned schema objects are **not**
   mutated — the standalone MCP stdio servers still require `binary_path` from their own clients, so
   the agent path and the stdio path (ADR: "identical code") stay consistent.

`dispatch`'s `binary_path` is a **required** keyword argument: there is no silent fallback to a
model-supplied path, so the confinement invariant cannot be reintroduced by a caller forgetting to
pass it.

## Consequences

**Positive:**

- The analysis tools work: the agent can enumerate/disassemble/decompile the real target instead of
  hitting `binary not found` on every host-side call. Trial 2 measures capability, not plumbing.
- The tools are confined to the run's target — a model cannot direct a host-side analysis tool at an
  arbitrary file. This tightens the ethical/sandbox posture (ADR 0002) without adding an execution
  path.
- The model's prompt surface shrinks: analysis tools that only took `binary_path` now advertise an
  empty input, so the model calls them with `{}` and cannot be confused about which path to pass.

**Negative / limitations (recorded honestly):**

- Tool result payloads still echo the injected host path back to the model (e.g. the gadget-list
  header, ghidra's `binary_path` field). This leaks the lab-host path into the transcript. It is
  harmless (the path is not secret and the model cannot act on it — it cannot choose the file), but it
  is not hidden; a future tightening could redact it.
- Comparability with the confounded first Trial-2 shakeout run is broken by design — those runs could
  not reach the analysis tools at all. That partial run is not a valid data point and is excluded.

## Alternatives considered

- **Tell the model the real host path in the prompt.** Rejected: it re-exposes the confinement hole
  (the model could then name any path), leaks host layout as a first-class instruction, and adds a
  second path string for the model to confuse with `/work/target`.
- **Store `binary_path` on the ToolLayer at construction.** Rejected: the ToolLayer is built before
  the per-run binary is known (`_default_config`, tests, `harness/runner.py`), whereas
  `state.binary.binary_path` is always present and authoritative at dispatch. Threading it through
  `dispatch` keeps the layer a stateless dispatcher.
- **Make the analysis tools run inside the sandbox so `/work/target` resolves.** Rejected: it would
  put ROPgadget/ghidra/radare2 execution inside the payload sandbox, multiplying execution surface
  against the single-execution-point rule (ADR 0002/0016). Analysis is read-only host tooling by
  design; only the validator runs payloads.

## Ethical scope

Unchanged and slightly strengthened. Educational/CTF targets only, proof-of-concept payloads only, one
sandboxed execution point (ADR 0002/0016). This ADR grants no new capability and no new execution
surface; it removes the model's ability to choose which host file the analysis tools read, confining
them to the run's designated target.
