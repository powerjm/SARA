# cb-multios corpus build recipe

Reproducible build of the DARPA CGC corpus binaries (the `cgc-*` entries in
`corpus/manifest.yaml`) as clean static-address ROP targets. Everything compiles
inside a Docker container, so **no host toolchain install (or sudo) is needed** —
only `docker`, `git`, and the repo `.venv`.

## One command

```bash
corpus/scripts/cb-multios/build.sh            # checkout -> image -> build -> pin+install
# or point at an existing checkout:
corpus/scripts/cb-multios/build.sh ~/src/cb-multios
```

This clones cb-multios at the commit pinned in the manifest's `source_url`, builds
the toolchain image, builds the targets, then runs
`python -m corpus.scripts.build --all --cb-multios <checkout> --update` to hash,
pin, and install the ELFs into `corpus/binaries/`.

## What it produces

i386 ELFs that are **EXEC (non-PIE) / NX enforced / no stack canary / no RELRO /
statically linked**, matching `protections: [nx]`. Static linking is required:
the validator sandbox (`validator/runner.py`) mounts *only* the ELF, so it must
carry `libcgc`/`libc` itself (the stock cb-multios shared build needs `libcgc.so`
via an absolute rpath that doesn't exist in the sandbox).

## Files

| File | Role |
|------|------|
| `Dockerfile` | ubuntu:22.04 + multilib/clang/cmake toolchain (upstream's 18.04 image is too old for HEAD's CMake). |
| `build_targets.sh` | Runs in-container: patches the cb-multios exec-stack default, configures i386/static/non-PIE/NX, builds the 5 targets. |
| `build.sh` | Host one-shot wrapper that drives all of the above. |

## The non-default changes (why the SHAs are what they are)

The pinned SHA-256s record *this* recipe; reproduce them with the same toolchain.
Two deviations from a stock `./build.sh`:

1. **Protections flags** at configure time (`-no-pie -fno-stack-protector`,
   static libs, `-Wl,-z,noexecstack`) — turn the DECREE-style "no protections"
   default into a non-PIE / NX target with fixed gadget addresses.
2. **One-line patch** to cb-multios `CMakeLists.txt`: its
   `-z execstack -z norelro` (appended *after* our linker flags) is flipped to
   `-z noexecstack -z norelro` so NX actually sticks. `build_targets.sh` applies
   this idempotently with `sed`.

## Challenge name mapping

cb-multios renames each challenge; the original CGC id is recovered from
`AUTHOR_ID`/`SERVICE_ID` in each `CMakeLists.txt` (see
`docs/CGCQualifyingEventChallengeMapping.md` in the checkout). Each manifest
entry carries the resolved dir under `build.challenge`:

| Manifest id | CGC id | cb-multios dir |
|-------------|--------|----------------|
| `cgc-cadet-00001` | CADET_00001 | `Palindrome` |
| `cgc-cromu-00004` | CROMU_00004 | `PCM_Message_decoder` |
| `cgc-cromu-00001` | CROMU_00001 | `basic_messaging` |
| `cgc-kprca-00007` | KPRCA_00007 | `router_simulator` |
| `cgc-cromu-00002` | CROMU_00002 | `Particle_Simulator` |
