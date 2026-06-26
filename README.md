# Sans Agentic Rop Analysis (SARA)

**Agentic AI for Automated Binary Vulnerability Analysis**

Companion code to Jeff Powers' SANS.edu thesis *Agentic AI for Automated Binary Vulnerability Analysis: Creating LLM-Based Agents for Return-Oriented Programming (ROP) Exploitation*. This repository is the testing framework used in the paper, with agentic workflows whose backend-LLMs can be swapped out, which performs automated data collection and analysis of a curated list of ROP-exploitable applications (the `corpus`). The thesis reports findings produced by it; this repo explains how to build and run it.

> Detailed architectural rationale is in [`docs/INFRASTRUCTURE_PLAN.md`](docs/INFRASTRUCTURE_PLAN.md). Read it before making non-trivial changes — most "why is it this way?" answers are there.

---

## Project status

Development followed one linear plan — eight steps, done in order, each shipped complete (no leftover stubs) before the next. The full step-by-step record is in [`docs/SARA_DEVELOPMENT_HISTORY.md`](docs/SARA_DEVELOPMENT_HISTORY.md).

| Step | Milestone | Status |
|-----:|-----------|--------|
| 0 | Environment works on Ubuntu 26.04 / Python 3.14 | **done** |
| 1 | Test data: real binary + synthetic dataset | **done** |
| 2 | ROPgadget MCP server (the worked tool) | **done** |
| 3 | Validator sandbox (the only execution path) | **done** |
| 4 | Agent loop, end-to-end on a fake backend | **done** |
| 5 | `sara run` + `sara batch` produce real data | **done** |
| 6 | Analysis notebooks turn data into Findings | **done** |
| 7 | Every backend + every tool | **done** |
| 8 | Run for record: hardened, reproducible, local or cloud | in progress |

---

## Prerequisites

A minimal Ubuntu 26.04 image ships Python 3.14, `git`, and binutils, but **not** a C toolchain or the binary-analysis tools. Install everything a lab host needs in one shot:

```bash
sudo apt install -y \
  build-essential curl ca-certificates \
  python3.14 python3.14-venv python3-pip \
  gdb gdbserver radare2 \
  openjdk-21-jdk \
  docker.io docker-buildx
sudo usermod -aG docker "$USER"        # log out/in for the group to take effect
```

CI only needs the build + Docker subset; the binary tools (`gdb`, `radare2`, Ghidra) are lab-host only. For 32-bit corpus targets also install `gcc-multilib libc6-i386`.

> All Python libraries and applications are *pinned* to specific versions to promote repeatability. Using a different version of Python (or a base OS different than Ubuntu 26.04) may require significant tweaks to `pyproject.toml`, and CI pipelines and github workflows will fail.

## Quick start

```bash
# 1. Clone and enter
git clone <repo-url> sara && cd sara

# 2. Bootstrap (creates venv, installs pinned deps, sets up pre-commit)
make bootstrap
.venv/bin/pip install ROPgadget ropper    # Python-based binary tools

# 3. Verify everything works
make test
make sandbox-build                        # build the validator sandbox image

# 4. Run against the sample binary (once you have a backend key)
cp .env.example .env   # edit and add your ANTHROPIC_API_KEY (or another)
python -m harness.cli run --binary sample-overflow --backend claude-sonnet
```

## Running locally vs in the cloud

The apparatus runs identically in both — same code, same Docker validator, same `RunRecord` output. Only the host and `.env` differ.

- **Local** (default): everything on one Ubuntu 26.04 host. Cloud backends use API keys in `.env`; open-weight and unrestricted models run through a local [LM Studio](https://lmstudio.ai) endpoint. Best for development and small matrices.
- **Cloud**: the same stack on a reproducible VM built from [`infra/packer/`](infra/) and provisioned with [`infra/terraform/`](infra/). Best for the full matrix at scale and the hardware baseline the thesis cites. A GPU instance is needed only to run local models in the cloud.

See [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md) for the full run procedure and [`docs/SARA_DEVELOPMENT_HISTORY.md`](docs/SARA_DEVELOPMENT_HISTORY.md) for how the apparatus was built and what each environment requires.

---

## Repository layout

> If you're picking up development from here, read [`docs/SARA_DEVELOPMENT_HISTORY.md`](docs/SARA_DEVELOPMENT_HISTORY.md) first — the step-by-step record of how the apparatus was built, with each step's acceptance criteria and the decisions it resolved.

```
sara/
  agent/                  LangGraph state machine, prompting strategies
  backends/               One module per LLM backend implementation
  mcp_servers/            MCP servers wrapping binary-analysis tools
    ropgadget/            ROPgadget server (the worked tool example)
    ghidra/ radare2/ ropper/ pwntools/ gdb/    Remaining tool servers
  validator/              Sandbox runner + outcome classification
  corpus/
    manifest.yaml         Binary corpus metadata (in git)
    binaries/             Binaries themselves (gitignored)
    exploits/             Documented exploit scripts
    scripts/              fetch.py, build.py, verify.py
  harness/                CLI run harness + run-record schema
  analysis/               Statistical module (Cochran's Q, McNemar's, etc.)
  docs/                   Infrastructure plan, ADRs, reproduction guide
  infra/                  Terraform/Packer for the cloud VM image
  tests/                  pytest suite
  scripts/                Dev helper scripts
  Dockerfile.sandbox      Frozen toolchain for the validator sandbox
  pyproject.toml          Pinned Python dependencies
  Makefile                Common dev tasks
```

---

## Ethical scope

This repository builds tooling that constructs Return-Oriented Programming (ROP) exploit chains. Two non-negotiable guardrails govern its use:

1. **Educational targets only.** The binary corpus consists of intentionally vulnerable, publicly-distributed binaries (SANS coursework, CTF challenges, DARPA Cyber Grand Challenge samples, ISPRAS ROP Benchmark). No production software, no real-world targets.
2. **Proof-of-concept payloads only.** Generated payloads demonstrate control flow hijack against the success marker defined in the corpus manifest. No weaponized shellcode, no persistence mechanisms.

The above non-negotiable guardrails apply to both humans and computers (computers being broadly defined as any form of AI, Agent, LLM, or automated software process).

The above non-negotiable guardrails have been applicable since the creation of this project, will be in place forever, and are applicable to any copies, forks, or derived works of this project.

Use against systems you do not own or have not been authorized to test is prohibited.

---

## License

See `LICENSE`. Note that corpus binaries retain the licenses of their original distributors; the manifest records the source and licence for each entry.

---

## Citation

If you use this code for future research, check out the associated paper with the results:

> Powers, J. (2026). *Agentic AI for Automated Binary Vulnerability Analysis: Creating LLM-Based Agents for Return-Oriented Programming Exploitation.* Master's thesis, SANS Technology Institute.
