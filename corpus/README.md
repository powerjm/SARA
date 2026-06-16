# Binary corpus

The experimental ground truth. Each binary is intentionally vulnerable with a publicly-documented working exploit chain. The corpus is small (5–10 entries) by design — see "Threats to validity" in the thesis for the rationale.

## Manifest

`manifest.yaml` describes each binary. Required fields:

| Field | Meaning |
|-------|---------|
| `id` | Slug used as the foreign key in run records. |
| `name` | Human-readable label. |
| `source_url` | Where the binary is fetched from. |
| `sha256` | SHA-256 of the binary; verified at fetch time. |
| `architecture` | `x86_64`, `i386`, `arm`, ... |
| `protections` | Subset of `nx`, `pie`, `relro`, `canary`, `aslr`. |
| `difficulty_tier` | 0 (trivial) – 3 (research-grade), set by the experimenter. |
| `documented_vuln_class` | e.g. `stack_overflow`. |
| `documented_exploit_url` | Writeup or PoC location. |
| `documented_gadget_addresses` | Addresses in the documented chain (used by classifier). |
| `success_marker` | String the validator checks for on stdout. |
| `license` | Original license of the binary. |
| `training_data_leakage_risk` | `low`/`medium`/`high` — disclosed in results. |
| `notes` | Free-form. |

## Layout

```
corpus/
  manifest.yaml         <- IN GIT, source of truth
  binaries/             <- GITIGNORED, populated by fetch.py / build.py
  exploits/             <- Documented exploit scripts (Phase 4)
  scripts/
    fetch.py            <- downloads + sha256-checks per manifest
    build.py            <- builds-from-source (cb-multios) + sha256-pins
    verify.py           <- reproduces documented exploit (Phase 4 stub)
```

## Two ways a binary gets into `binaries/`

Most entries are **download-and-hash**: `source_url` points at a prebuilt
artifact that `fetch.py` downloads and checks against `sha256`.

The DARPA CGC entries are **build-from-source**. The original CGC binaries target
DECREE and will not run in the validator sandbox, so we use the Trail of Bits
Linux port [`trailofbits/cb-multios`](https://github.com/trailofbits/cb-multios)
(MIT), which produces native Linux ELFs. cb-multios *renames* each challenge
directory, so these entries carry a `source_url` of the form
`git+https://github.com/trailofbits/cb-multios@<commit>` and are resolved by the
original CGC id (derived from the manifest `id`, e.g. `cgc-cromu-00004` ->
`CROMU_00004`). `fetch.py` skips `git+` sources; `build.py` handles them.

## Bootstrapping a new corpus

```bash
# 1. Add an entry to manifest.yaml.

# 2a. Download-and-hash entries (SHA256 mismatch is fatal):
python -m corpus.scripts.fetch

# 2b. Build-from-source (CGC / cb-multios) entries: build cb-multios first
#     (per its README, e.g. ./build.sh), then resolve + hash + install. First
#     time, --update pins the SHA your toolchain produced (commit it):
python -m corpus.scripts.build --all --cb-multios ~/src/cb-multios --update
python -m corpus.scripts.build --id cgc-cromu-00004 --cb-multios ~/src/cb-multios
#     ...or install an explicit pre-built ELF, bypassing resolution:
python -m corpus.scripts.build --id cgc-cromu-00004 --from /path/to/built/Audio_Decoder

# 3. Verify each entry's documented exploit actually fires the success marker:
python -m corpus.scripts.verify
```

> The cb-multios build is not guaranteed byte-identical across toolchains, so a
> CGC entry's `sha256` pins *your* lab-host build (as the fixture's `build.sh`
> does). Re-pin deliberately with `--update` when the toolchain changes.

## Why the corpus is small

The thesis methodology pairs each backend against every binary, then applies nonparametric repeated-measures tests (Cochran's Q + McNemar's; Friedman's + Wilcoxon). These tests are powered by the number of *binaries*, but the ground-truth completeness cost grows roughly linearly with corpus size and is the dominant constraint here.
