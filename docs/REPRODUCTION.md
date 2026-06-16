# Reproducing the experiments

This guide records exactly what an outside reader needs to re-run the experiments reported in the thesis. The aim is for someone with no prior context to reach the published results given only this file, the repo, and backend API credentials.

## 1. Environment

- Linux host (Ubuntu 26.04 LTS tested and used for runs for record).
- Python 3.14.
- Docker 24+ (validated on 29.1.3; add your user to the `docker` group).
- ~20 GB free disk.
- (Cloud) the VM image built from `infra/packer/` is the official hardware baseline.

### System packages

A minimal Ubuntu 26.04 image ships Python 3.14, `git`, and binutils, but **not**
a C toolchain or the binary-analysis tools — `make bootstrap` and the fixture
build fail until you install them. One command covers a lab host:

```bash
sudo apt install -y \
  build-essential curl ca-certificates \
  python3.14 python3.14-venv python3-pip \
  gdb gdbserver radare2 \
  openjdk-21-jdk \
  docker.io docker-buildx
sudo usermod -aG docker "$USER"               # log out/in for the group to take effect
.venv/bin/pip install ROPgadget ropper        # Python-based binary tools (after bootstrap)
# Ghidra (Step 7 only): download the release, unzip to /opt/ghidra, add it to PATH (JDK 21).
```

Notes: CI needs only the `build-essential` + Docker subset (the binary tools are
lab-host only). Add `gcc-multilib libc6-i386` for 32-bit corpus targets.
`python3.14-dev` / `libffi-dev` / `libssl-dev` are not needed on 26.04 — every
dependency installed from a prebuilt 3.14 wheel.

## 2. Clone and bootstrap

```bash
git clone <repo-url> sara
cd sara
make bootstrap
make test         # confirm the suite passes
```

## 3. Credentials

```bash
cp .env.example .env
$EDITOR .env      # fill in API keys
```

For local backends, start LM Studio and load the model named in `backends.registry`.

## 4. Corpus

```bash
python -m corpus.scripts.fetch     # downloads + sha256-verifies binaries
python -m corpus.scripts.verify    # confirms each documented exploit fires
```

Fetch will fail loudly if any binary is missing a `source_url` or `sha256` in `corpus/manifest.yaml`. Verify will fail if any documented exploit no longer reproduces in the validator sandbox. Do not proceed past this step with failures.

## 5. Sandbox image

```bash
make sandbox-build
```

This builds `sara-sandbox:latest`. Pin its digest in `.env` (`VALIDATOR_IMAGE=sara-sandbox@sha256:...`) before running the experiment matrix.

## 6. Single run

```bash
python -m harness.cli run \
    --binary sample-overflow \
    --backend claude-sonnet \
    --strategy zero_shot
```

A successful run writes `runs/<uuid>/{record.json, trace.jsonl, payload.bin}`.

## 7. Full experiment matrix

Create `experiments.yaml` with the binary × backend × strategy × replicate matrix, then:

```bash
python -m harness.cli batch --config experiments.yaml
```

Plan for total wall-clock and API spend by counting cells × replicates and multiplying by the historical per-run averages logged in the README of the runs you most recently completed.

## 8. Analysis

```bash
jupyter lab analysis/notebooks
```

Run notebooks 01–07 in order. Each emits a Markdown summary at the bottom that can be copied directly into the thesis Findings section.

## 9. Submission package

For the thesis defence packet:

1. Run records: zip `runs/` excluding `payload.bin` files larger than the    submission size cap. Keep the SHA-256 of every excluded payload in `RunRecord.notes`.
2. Notebooks: `jupyter nbconvert --to html analysis/notebooks/*.ipynb` and commit the HTMLs to `docs/analysis_html/`.
3. Apparatus snapshot: `git archive --format=zip HEAD -o sara-snapshot.zip`.

The submission package, the thesis Word document, and the corpus manifest together suffice for an independent re-run.

## Known issues

Recorded during the Step 0 environment validation (2026-06-14) on a real
Ubuntu 26.04 LTS host (Python 3.14.4, Docker 29.1.3).

- **No dependency pins needed bumping.** A fresh `pip install -e ".[dev,analysis]"`
  resolved every dependency from prebuilt 3.14 wheels — scipy 1.17.1, numpy 2.4.6,
  pandas 2.3.3, pydantic 2.13.4, mypy 1.20.2, etc. The migration's pins are good.
- **`make`/`gcc` absent on a minimal image.** See "System packages" above —
  install `build-essential` before `make bootstrap`.
- **pytest-asyncio + Python 3.14 deprecation.** pytest-asyncio 0.26's autouse
  `event_loop_policy` fixture calls `asyncio.get_event_loop_policy()`, which 3.14
  deprecates (removal in 3.16). Under the repo's strict `filterwarnings = ["error"]`
  this errored all 68 tests. Fixed with a scoped ignore in
  `[tool.pytest.ini_options]` (message-matched, so the strict policy still applies
  to our own code). Remove the ignore once pytest-asyncio drops the call.
- **ruff version drift (open — needs a decision).** `ruff` is pinned only
  `>=0.8.0,<1.0`, so bootstrap pulled 0.15.17, which re-flags the committed code:
  19 lint findings (mostly import ordering) and 12 files `ruff format` would
  rewrite, including high-review-cost files (`harness/record.py`,
  `analysis/aggregate.py`). CI would fail lint as-is. Resolve by either pinning
  ruff to the version the code was formatted with, or running a dedicated
  `ruff format` + `ruff check --fix` pass (separate commit, not folded into a
  feature change). Not done here to keep the Step 0 change minimal.
- **mypy: 61 errors across 6 files.** Advisory only at this early stage
  (strict mode, stubs still firming up per the working agreement); not a gate.
