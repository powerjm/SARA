# ADR 0004 — Ghidra is driven through PyGhidra, pinned to Ghidra 11.4.3 + JDK 21

Status: Accepted (decided 2026-06-15; implemented with the Ghidra MCP server in Step 7)

## Context

The tool layer is a set of per-tool MCP stdio servers, each following the
worked-example pattern from `mcp_servers/ropgadget/server.py`: a plain,
unit-testable Python function plus a thin MCP shell. ROPgadget shells out to a
CLI, so its Python wrapper is trivial. Ghidra is different: it is a large Java
application, and the five tools the Ghidra server must expose
(`disassemble_function`, `decompile_function`, `list_imports`, `list_strings`,
`get_xrefs` — see `mcp_servers/ghidra/README.md`) all need access to a live,
already-analysed Ghidra program. Re-running headless analysis on every call is
far too slow, so the server must analyse a binary **once** and reuse the open
program across calls.

Two things therefore have to be decided before the server can be built:

1. **How Python talks to Ghidra (the "bridge").** The candidates are
   `ghidra_bridge` (a third-party RPC bridge into a running headless Ghidra),
   **PyGhidra** (Ghidra's own integrated CPython/JPype interface, shipped in the
   distribution since the 11.x line), or repeated `analyzeHeadless` invocations
   with post-scripts.
2. **Which Ghidra and JDK versions to pin.** This is a *reproducibility*
   requirement, not a packaging detail: Ghidra's decompiler output is fed to the
   agent as reasoning context, so a different Ghidra release can change the
   experiment's results. The pinned versions go into the replication snapshot
   (ADR-adjacent: `docs/REPLICATION_SNAPSHOT.md`, Step 8) and the cloud image
   (`infra/packer/`). The host runs Python 3.14, so whatever bridge we pick must
   support CPython 3.14.

This is flagged as the last open decision on Step 7 of
`docs/SARA_DEVELOPMENT_HISTORY.md`.

## Decision

The Ghidra MCP server drives Ghidra through **PyGhidra**, pinned to
**Ghidra 11.4.3** running on **JDK 21**.

- **PyGhidra** is Ghidra's first-party integration: a native CPython 3
  interpreter with direct access to the Ghidra API via JPype, launched from the
  distribution's support scripts. It supports CPython 3.9–3.14, so it runs on the
  sara 3.14 host with no separate interpreter. Because it ships *inside* the
  Ghidra distribution, pinning the Ghidra version pins the bridge too — there is
  no independently-versioned bridge package to track.
- **Ghidra 11.4.3** is the latest patch of the mature 11.x line. The 11.3+ line
  requires **JDK 21** as its minimum, which is already what `README.md`,
  `docs/REPRODUCTION.md`, and `infra/packer/README.md` install, so the pin is
  consistent with the environment already documented.
- The server **analyses each binary once** (opening a project / program) and
  reuses that program for every subsequent tool call within the server's
  lifetime; JVM + analysis startup cost is paid once at first use, not per call.
- Ghidra is a **lab-host / cloud-image-only** dependency. As with ROPgadget
  (`requires_ropgadget`), the Ghidra integration tests **skip, not fail**, when
  Ghidra/JDK are absent, so CI does not need Ghidra installed.

The exact pin lives in the install docs and the cloud image build, and the
version string is captured in the replication snapshot.

## Consequences

**Positive:**

- **First-party and self-contained.** No third-party RPC package to pin, patch,
  or keep compatible with the Ghidra version; the bridge and the tool move as one
  artifact. One fewer moving part in the replication snapshot.
- **Native Python 3.14.** PyGhidra's CPython range tops out at exactly 3.14, so
  the server runs in the same interpreter family as the rest of the apparatus.
- **Reproducible.** A single pinned (Ghidra, JDK) pair means decompiler output —
  which the agent reasons over — is stable across the lab host and the cloud VM.
- **Fast steady state.** Analyse-once / reuse-program keeps per-call latency low
  after the one-time JVM + analysis cost.

**Negative:**

- **Coupled to Ghidra internals.** PyGhidra calls the Ghidra API directly, so a
  future Ghidra upgrade can break the server in ways a process-boundary RPC
  bridge might have absorbed. Mitigated by pinning the version and only upgrading
  deliberately (a new ADR or an explicit pin bump).
- **JVM weight.** Each Ghidra server process carries a JVM; running it is
  heavier than the ROPgadget CLI wrapper. Acceptable — it is one server, started
  on demand, lab-host-only.
- **Not exercised on CI.** Like the other binary tools, the real Ghidra path is
  only tested on the lab host; CI runs fixture-based parser tests and skips the
  integration tests.

## Alternatives considered

- **`ghidra_bridge` (third-party RPC).** Rejected. It is mature and decouples
  the Python side from Ghidra's internals across a process boundary, but it adds
  a separately-maintained, independently-versioned dependency to pin and keep
  compatible with each Ghidra release — exactly the kind of drift the
  replication snapshot is meant to avoid. With PyGhidra now first-party, the
  third-party bridge's main advantage (Python access at all) is no longer unique
  to it.
- **`analyzeHeadless` per call.** Rejected. Shelling out to the headless
  analyzer with post-scripts on every tool call re-runs full auto-analysis each
  time, which is prohibitively slow for an interactive agent loop. This is the
  approach `mcp_servers/ghidra/README.md` already warns against.
- **Ghidra 12.0.x (the newer major line).** Rejected for now. It is newer than
  11.4.3 and may carry a different JDK requirement and less field-testing; for a
  thesis instrument we prefer the latest patch of the established 11.x line,
  which keeps the JDK-21 assumption already baked into the docs. Revisit with a
  pin bump if a 12.x capability is needed.
