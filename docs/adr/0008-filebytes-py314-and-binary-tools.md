# ADR 0008 — `binary-tools` extra on Python 3.14: vendor a patched `filebytes`, drop unused `pwntools`

Status: Accepted (decided 2026-06-25; Step 8 run-for-record hardening)

## Context

sara targets **Python 3.14 / Ubuntu 26.04** (`pyproject.toml`, `README.md`). The
lab-host binary-analysis tooling installs through the `binary-tools` optional
extra. While making every MCP tool server actually operational on the target
host, two members of that extra turned out to be **uninstallable on Python 3.14**,
so `pip install -e ".[binary-tools]"` — the command the docs and the Packer image
(`infra/packer/provision/install-tools.sh`) tell you to run — failed outright:

1. **`ropper` → `filebytes`.** `ropper` requires `filebytes`, whose `setup.py`
   metadata extractor uses `ast.Str` and `node.s`. Both were deprecated in
   Python 3.8 and **removed in 3.12**, so *no* released `filebytes` (latest 0.10.2)
   builds from sdist on 3.14, and `filebytes` ships no wheel. The failure is at
   build time, in metadata extraction only — the runtime package is fine.
2. **`pwntools` → `unicorn`.** `pwntools` pins an older `unicorn` that has no
   cp314 wheel and fails to build from source on this host. But **nothing in the
   apparatus imports `pwn`**: the pwntools MCP server deliberately reimplements
   the small slice it needs (little-endian packing, De Bruijn cyclic patterns) in
   pure Python (see `mcp_servers/pwntools/server.py`'s docstring), precisely so it
   has no native dependency and is testable on CI. `pwntools` in the extra was
   therefore dead weight that also broke the install.

This is a reproducibility concern (it touches the pinned dependency set), so it
gets an ADR per the working agreement.

## Decision

- **Vendor a one-line-patched `filebytes` wheel** in `vendor/filebytes/` and
  install it *before* the extra so `ropper`'s `filebytes>=0.10.0` requirement is
  already satisfied and pip never builds the broken sdist. The patch swaps
  `ast.Str`/`.s` for `ast.Constant`/`.value` (`vendor/filebytes/ast-str-py312.patch`);
  it touches build-time metadata only, leaving the runtime package byte-for-byte
  upstream 0.10.2. The wheel's sha256 and a rebuild-from-upstream recipe are
  recorded in `vendor/filebytes/README.md`.
- **Remove `pwntools` from the `binary-tools` extra.** It is unused and
  unbuildable on 3.14. The pwntools MCP server stays fully operational (it never
  imported `pwntools`). Anyone wanting interactive pwntools on a lab host can
  `pip install pwntools` separately where it builds.

The install order — vendored wheel, then extra — is wired into the Packer
provisioner, `README.md`, and `docs/REPRODUCTION.md`.

## Consequences

**Positive:**

- `pip install -e ".[binary-tools]"` succeeds on the Python 3.14 target, so the
  radare2 and ropper MCP servers are installable and operational (previously the
  extra failed before installing anything).
- The `filebytes` fix is pinned and auditable (committed wheel + patch + sha256 +
  rebuild recipe) rather than a manual lab-host hack.
- The extra now matches what the apparatus actually uses; no native `unicorn`
  build is attempted.

**Negative:**

- A vendored binary wheel lives in the repo. Mitigated by committing the patch
  and provenance alongside it, and by the note to drop it once upstream
  `filebytes` publishes a 3.12+ compatible release.
- Anyone who relied on `pwntools` arriving via the extra must install it
  explicitly. Acceptable: nothing in the apparatus uses it.

## Alternatives considered

- **Pin `filebytes` from a patched git fork.** Reproducible but adds an external
  git ref to track and a network dependency at install time; a committed wheel +
  patch is more self-contained for the replication snapshot.
- **Drop `ropper` entirely.** Rejected: ropper complements ROPgadget (different
  filters / gadgets), and that comparison is part of the failure-mode analysis.
- **Keep `pwntools` and pin a 3.14-compatible `unicorn`.** Rejected: it is unused,
  so carrying it (and chasing its native-build compatibility) buys nothing.
- **Leave the patched-wheel build as a documented manual step.** Rejected: it
  would leave the canonical `pip install -e ".[binary-tools]"` broken on the
  target until upstream fixes `filebytes`, which undercuts reproducibility.
