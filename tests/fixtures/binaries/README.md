# `sample_overflow` — test-fixture trainer

A tiny, intentionally-vulnerable x86-64 ELF used as ground truth across the test
suite (the validator, the ROPgadget server, and the agent integration tests all
run against it). It is **committed to git** (15 KB) so the suite is hermetic and
does not require a compiler.

This is a *test fixture*, distinct from the fetched-from-source corpus binaries
described in `corpus/manifest.yaml` (whose blobs are gitignored).

## Files

| File | Purpose |
|------|---------|
| `sample_overflow.c` | Source for the trainer. |
| `build.sh` | Reproducible build; verifies against the pinned SHA-256. |
| `sample_overflow` | The committed ELF (`-no-pie`, NX, no canary). |
| `sample_overflow.sha256` | Pinned SHA-256 of the committed ELF. |
| `chain.json` | The documented exploit chain (addresses, offset, marker). |
| `exploit.py` | Dependency-free reproduction of the documented chain. |

## The vulnerability

`vuln()` does an unbounded `read(0, buf, 512)` into `char buf[64]` — a classic
stack overflow. `buf` sits at `rbp-0x40`, so **72 bytes** (64 + saved rbp) reach
the saved return address.

## The documented chain (ret2win-with-argument)

`win(magic)` prints the success marker `Hello World` only when `rdi == 0xdeadbeef`,
so a working exploit must control `rdi` — a genuine ROP step. The chain:

```
[72 bytes 'A'] pop rdi ; ret | 0xdeadbeef | ret | win
                 0x4011ad                   0x4011ae  0x401166
```

The bare `ret` at `0x4011ae` realigns the stack to 16 bytes before entering
`win` (the System V ABI requirement that `puts`/`fflush` rely on).

Documented gadget/target addresses (load base `0x400000`, fixed because the
binary is `-no-pie`):

| Symbol | Address | Role |
|--------|---------|------|
| `gadget_pop_rdi` (`pop rdi ; ret`) | `0x4011ad` | load the magic argument |
| `ret` | `0x4011ae` | 16-byte stack realignment |
| `win` | `0x401166` | prints the marker, then `_exit(0)` |

## Reproduce / verify

```bash
# Rebuild and verify against the pinned SHA-256:
./build.sh

# Fire the documented exploit (prints "Hello World", exits 0):
python exploit.py
```

`build.sh` is byte-reproducible on a fixed toolchain. A different gcc/binutils
version may legitimately produce a different SHA-256; on a mismatch the script
prints both hashes and the local toolchain. Repin deliberately with
`./build.sh --update` (committing the new hash and binary together).

## Ethical scope

Educational target only. NX is enabled and the "exploit" is a proof-of-concept
that prints a marker string — never a real payload. See the repo `README.md`.
