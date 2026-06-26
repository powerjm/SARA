# Replication snapshot

The replication snapshot is the reproducibility bundle behind the thesis's
reported results. It packages the apparatus, the exact environment, and the data
so that an independent reviewer can **re-validate every payload** — confirming
the reported successes still fire — without re-running a single LLM agent or
paying for a single token. This is what makes the data trustworthy: the
expensive, stochastic step (the agent) is recorded; the cheap, deterministic
step (executing the payload in the sandbox) is re-run.

Two scripts implement it:

- [`scripts/build_replication_snapshot.sh`](../scripts/build_replication_snapshot.sh) — assemble the bundle.
- [`scripts/verify_snapshot.sh`](../scripts/verify_snapshot.sh) — re-validate it.

## Building a snapshot

Run it from a bootstrapped repo on the host that produced the runs:

```bash
scripts/build_replication_snapshot.sh            # snapshots HEAD + ./runs
# options:
#   --ref REF          repo ref to archive (default HEAD; use a tag for record)
#   --out DIR          output directory (default dist/)
#   --runs DIR         run-records directory (default $RUN_OUTPUT_DIR or ./runs)
#   --no-binaries      record corpus checksums only, not the binary bytes
#   --no-notebooks     skip rendering analysis notebooks to HTML
```

It honors the same `SARA_CORPUS_MANIFEST` / `SARA_CORPUS_BINARIES_DIR` overrides
the harness uses, so the snapshot reflects exactly the corpus the runs resolved
against. Set `SARA_RUN_ENV=local` or `SARA_RUN_ENV=cloud` so the environment
summary records which of the [two run environments](SARA_DEVELOPMENT_HISTORY.md#two-ways-to-run)
produced the data.

Output: `dist/sara-snapshot-<commit>.tar.zst` (+ a `.sha256`). Contents:

| Entry | What it is |
|-------|------------|
| `source-<commit>.tar.gz` | the repo tree at the chosen ref (`git archive`) |
| `pip-freeze.txt` | exact installed Python package versions |
| `validator-image.txt` | the sandbox Docker image id + repo digest |
| `manifest.yaml` | the corpus metadata catalog |
| `corpus-binaries/` | the corpus binaries (omitted with `--no-binaries`) |
| `corpus-binaries.sha256` | corpus binary checksums (always present) |
| `runs/` | every finalized run directory (`record.json` / `trace.jsonl` / `payload.bin`) |
| `payloads.sha256` | checksums of every stored payload |
| `notebooks-html/` | executed analysis notebooks rendered to HTML |
| `environment.txt` | host / OS / CPU / RAM / Docker summary + local-vs-cloud |
| `SNAPSHOT.json` | machine-readable index |

> **Licensing.** Corpus binaries retain their original distributors' licenses
> (recorded per entry in `manifest.yaml`). The bundle includes the binaries by
> default so verification is self-contained; before distributing a snapshot
> publicly, use `--no-binaries` for any entry whose license forbids
> redistribution — the checksums still travel, and the verifier can run against
> binaries re-fetched from the manifest via `SARA_CORPUS_BINARIES_DIR`.

## Verifying a snapshot

On any bootstrapped host with Docker and the validator image built:

```bash
scripts/verify_snapshot.sh dist/sara-snapshot-<commit>.tar.zst
# or against an already-unpacked directory:
scripts/verify_snapshot.sh path/to/sara-snapshot-<commit>/
```

It will:

1. unpack the snapshot and check every payload against `payloads.sha256`
   (integrity / tamper check);
2. point the corpus resolver at the snapshot's own `manifest.yaml` +
   `corpus-binaries/`;
3. for each run with a payload, re-execute that payload in the real validator
   sandbox and confirm the fresh result reproduces the recorded
   `validator.succeeded` and `stdout_marker_found`.

It exits **0 only if every payload reproduced**; any mismatch, corruption, or
unresolvable binary is a non-zero exit and a per-run report. Runs without a
payload (e.g. refusals) are reported and skipped. The chain fingerprint is not
re-derived — it is a property of the proposer's chain and is already recorded;
verification confirms *execution*, which is the reproducible part.

### What verification does and doesn't prove

- **Does** prove: the stored payloads still drive the corpus binaries to the
  recorded outcomes in the locked-down sandbox, on the verifier's hardware.
- **Doesn't** prove: that the agent would make the same choices again (that step
  is stochastic and is captured, not re-run). Re-running the agent is a fresh
  experiment, not a verification.

## When to cut the record snapshot

Tag the commit, then build from the tag so `source-<commit>.tar.gz` and the
recorded commit match the thesis citation:

```bash
git tag -a v1.0-runs-for-record -m "thesis runs for record"
SARA_RUN_ENV=cloud scripts/build_replication_snapshot.sh --ref v1.0-runs-for-record
scripts/verify_snapshot.sh dist/sara-snapshot-*.tar.zst   # prove it before archiving
```

Keep the snapshot, its `.sha256`, and the thesis document together — with the
corpus manifest they suffice for an independent re-run.
