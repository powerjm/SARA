<!--
SARA — Sans Agentic Rop Analysis
Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
SPDX-License-Identifier: MIT
-->

# Backends — model catalog and cards

This directory is the model layer of SARA. Every experiment cell is a
`(binary, backend, prompting_strategy)` triple; the **backend** half is resolved
here. This README is the human-readable **model card reference** for every model
the thesis plans to test with — the machine-readable source of truth remains
[`registry.py`](registry.py) (which backend names exist, which model each serves,
and each one's `BackendCategory`) and [`pricing.yaml`](pricing.yaml) (rates for
the hosted models).

> **Ethical scope (non-negotiable, binds all copies/forks).** SARA targets
> **educational / CTF binaries only** and produces **proof-of-concept payloads
> only**. The `validator/` sandbox is the *only* component permitted to execute a
> payload (ADR 0002). The unrestricted models below are included to **measure**
> whether removing safety alignment changes an agent's willingness/ability to
> build ROP chains — not to broaden what SARA is pointed at. Use against systems
> you do not own or are not authorized to test is prohibited.

## Category definitions (ADR 0005)

Each `RunRecord` carries a `BackendCategory` as an **independent variable**, so it
is declared *a priori* per model (never derived from the run's behavior). The axis
is **safety-alignment status**, not license, host, or vendor:

| Category | Meaning | Served via |
|---|---|---|
| `PREMIUM` | Hosted frontier model behind a vendor API. | Anthropic / OpenAI / Google SDKs |
| `OPEN_WEIGHT` | Publicly downloadable weights **with safety/alignment tuning intact**, as released by the originating lab (standard instruct/chat releases). | Local LM Studio |
| `UNRESTRICTED` | Weights whose safety alignment has been **removed or was never present** — abliterated / "uncensored" community fine-tunes, or base models without instruction+safety tuning. | Local LM Studio |

`OPEN_WEIGHT` and `UNRESTRICTED` are served through the **same** LM Studio
endpoint ([`lmstudio_backend.py`](lmstudio_backend.py)); the category is the value
passed at registration, so the transport never has to distinguish them. See
[`../docs/adr/0005-backend-categories.md`](../docs/adr/0005-backend-categories.md)
for the full rationale (including why refusal rate — the *dependent* variable — is
deliberately **not** used to classify).

## Local hardware profile

The local run option targets a **single NVIDIA GeForce RTX 4090 (24 GB VRAM)** on
**Windows**, served through **LM Studio** (OpenAI-compatible endpoint, llama.cpp /
GGUF runtime). Every model in the `OPEN_WEIGHT` / `UNRESTRICTED` tables below —
except the two explicitly flagged — fits **entirely in 24 GB VRAM** at the noted
quantization with room for a working context, and has a GGUF build on Hugging
Face. Local models have **no per-token price**: cost is recorded as `usd=0.0` and
hardware cost is attributed from wall-clock instead (`CostRecord`).

**LM Studio wiring** ([`lmstudio_backend.py`](lmstudio_backend.py)): the endpoint
is `LMSTUDIO_BASE_URL` (default `http://127.0.0.1:1234/v1`); the API key is
ignored by LM Studio but a placeholder is sent. The **model string** in each
registry entry must match the *API identifier* of the model loaded in LM Studio —
rename the loaded model in LM Studio if it differs, or override via the backend
constructor. Determinism knobs: `temperature=0.2`, `seed=0` by default.

## Quick reference — `--backend` handles

`sara run --backend <handle>` resolves through [`registry.py`](registry.py):

| `--backend` handle | Model served | Category | 24 GB fit |
|---|---|---|---|
| `claude-sonnet` | claude-sonnet-4-6 (Anthropic API) | PREMIUM | n/a (hosted) |
| `claude-opus` | claude-opus-4-7 (Anthropic API) | PREMIUM | n/a (hosted) |
| `gpt-5` | gpt-5 (OpenAI API) | PREMIUM | n/a (hosted) |
| `gemini-2.5-pro` | gemini-2.5-pro (Google API) | PREMIUM | n/a (hosted) |
| `llama-3.3-70b` | llama-3.3-70b-instruct | OPEN_WEIGHT | ✗ ~42 GB (cloud/large-host) |
| `qwen2.5-coder-32b` | qwen2.5-coder-32b-instruct | OPEN_WEIGHT | ✓ tight (~20 GB) |
| `qwen2.5-coder-7b` | qwen2.5-coder-7b-instruct | OPEN_WEIGHT | ✓ (smoke-test only) |
| `qwen3-coder-30b` | qwen3-coder-30b-a3b-instruct | OPEN_WEIGHT | ✓ (~19 GB, MoE) |
| `gpt-oss-20b` | gpt-oss-20b | OPEN_WEIGHT | ✓ (~13 GB, MoE) |
| `devstral-small` | devstral-small-2507 | OPEN_WEIGHT | ✓ (~14 GB) |
| `dolphin-mixtral-8x7b` | dolphin-2.7-mixtral-8x7b | UNRESTRICTED | ✗ ~26 GB (over profile) |
| `whiterabbitneo-v3-7b` | whiterabbitneo-v3-7b | UNRESTRICTED | ✓ (~5 GB) |
| `qwen3-30b-abliterated` | qwen3-30b-a3b-abliterated | UNRESTRICTED | ✓ (~19 GB, MoE) |
| `dolphin-3.0-mistral-24b` | dolphin3.0-mistral-24b | UNRESTRICTED | ✓ (~14 GB) |

VRAM figures are the **Q4_K_M weight file** size (except gpt-oss, which ships
native MXFP4); add KV-cache/context on top. See [Fitting 24 GB](#fitting-24-gb).

---

## PREMIUM — hosted frontier models

These are the "premium tier from the frontier labs" the thesis keeps. Rates are
pinned in [`pricing.yaml`](pricing.yaml) (single source of truth) and snapshotted
into every `RunRecord`.

### claude-sonnet — Claude Sonnet 4.6
- **Vendor / API:** Anthropic Messages API.
- **Price (USD / Mtok):** 3.00 prompt / 15.00 completion.
- **Role:** premium mid-tier baseline; strong tool use for the agent loop.

### claude-opus — Claude Opus 4.7
- **Vendor / API:** Anthropic Messages API.
- **Price (USD / Mtok):** 5.00 prompt / 25.00 completion.
- **Role:** premium high-capability reference for long-horizon agentic ROP work.

### gpt-5 — GPT-5
- **Vendor / API:** OpenAI Chat Completions.
- **Price (USD / Mtok):** 1.25 prompt / 10.00 completion.
- **Role:** premium cross-vendor comparison (OpenAI).

### gemini-2.5-pro — Gemini 2.5 Pro
- **Vendor / API:** Google Gemini API.
- **Price (USD / Mtok):** 1.25 prompt / 10.00 completion (≤200k-token tier; the
  >200k tier is 2.50 / 15.00 and is *not* the pinned rate — revisit if prompts
  routinely exceed 200k).
- **Role:** premium cross-vendor comparison (Google).

---

## OPEN_WEIGHT — alignment intact, local

### llama-3.3-70b — Llama 3.3 70B Instruct
- **Developer:** Meta. **Arch:** dense, 70B. **Context:** 128K.
- **License:** Llama 3.3 Community License.
- **Weights / GGUF:** `meta-llama/Llama-3.3-70B-Instruct` · GGUF
  `bartowski/Llama-3.3-70B-Instruct-GGUF`.
- **24 GB fit:** ✗ **does not fit** — Q4_K_M ≈ 42 GB; usable only with heavy CPU
  offload (minutes/token). Kept as a **cloud / large-host** open-weight entry, not
  a 4090 run-for-record model.
- **Tool calling:** yes (native).

### qwen2.5-coder-32b — Qwen2.5-Coder-32B-Instruct
- **Developer:** Alibaba (Qwen). **Arch:** dense, 32B. **Context:** 32K native /
  128K via YaRN.
- **License:** Apache-2.0.
- **Weights / GGUF:** `Qwen/Qwen2.5-Coder-32B-Instruct` · GGUF
  `bartowski/Qwen2.5-Coder-32B-Instruct-GGUF`.
- **24 GB fit:** ✓ **tight** — Q4_K_M ≈ 20 GB; leaves limited room for context on
  a 24 GB card (drop to Q4_K_S or cap context if you hit OOM).
- **Tool calling:** yes; strong coding model.

### qwen2.5-coder-7b — Qwen2.5-Coder-7B-Instruct *(smoke-test, not run-for-record)*
- **Developer:** Alibaba (Qwen). **Arch:** dense, 7B. **Context:** 32K native /
  128K via YaRN.
- **License:** Apache-2.0.
- **Weights / GGUF:** `Qwen/Qwen2.5-Coder-7B-Instruct` · GGUF
  `bartowski/Qwen2.5-Coder-7B-Instruct-GGUF`.
- **24 GB fit:** ✓ trivially — Q4_K_M ≈ 5 GB.
- **Role:** smoke-testing the LM Studio transport and the agent tool loop on
  modest hardware. Same `OPEN_WEIGHT` label so an accidental real run is still
  correctly categorized. **Not** a run-for-record model.

### qwen3-coder-30b — Qwen3-Coder-30B-A3B-Instruct  *(new)*
- **Developer:** Alibaba (Qwen). **Arch:** MoE, **30.5B total / ~3.3B active**
  (128 experts, 8 active). **Context:** 256K native (up to 1M via YaRN).
- **License:** Apache-2.0.
- **Weights / GGUF:** `Qwen/Qwen3-Coder-30B-A3B-Instruct` · GGUF
  `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF` (the Unsloth build ships the fixed
  tool-calling chat template for llama.cpp / LM Studio) · also
  `bartowski/Qwen_Qwen3-Coder-30B-A3B-Instruct-GGUF`.
- **24 GB fit:** ✓ — Q4_K_M ≈ 18–19 GB; MoE means ~3.3B active → 7B-class speed
  (~176 tok/s on a 4090) at 30B quality.
- **Tool calling:** yes, native and strong — **top open-weight agentic-coding
  pick** and the primary local run-for-record candidate.

### gpt-oss-20b — OpenAI gpt-oss-20b  *(new)*
- **Developer:** OpenAI. **Arch:** MoE, **21B total / ~3.6B active** (32 experts,
  4 active). **Context:** 128K.
- **License:** Apache-2.0.
- **Weights / GGUF:** `openai/gpt-oss-20b` (ships a **native MXFP4** GGUF) · also
  `ggml-org/gpt-oss-20b-GGUF`, `unsloth/gpt-oss-20b-GGUF`.
- **24 GB fit:** ✓ comfortably — native MXFP4 ≈ 12–14 GB, large context headroom
  (~136 tok/s on a 4090).
- **Notes:** trained on OpenAI's **harmony** response format — a recent LM Studio
  parses this natively; o-series-style chain-of-thought suits multi-step
  gadget-chain planning. Native function calling. Different lab/architecture from
  Qwen → **provenance diversity** in the open-weight bucket.

### devstral-small — Mistral Devstral-Small-2507  *(new)*
- **Developer:** Mistral AI. **Arch:** dense, 24B (fine-tuned from
  Mistral-Small-3.1; vision encoder removed → text-only). **Context:** 128K.
  Tekken tokenizer (131k vocab).
- **License:** Apache-2.0.
- **Weights / GGUF:** `mistralai/Devstral-Small-2507` · GGUF
  `mistralai/Devstral-Small-2507_gguf` · also `unsloth/Devstral-Small-2507-GGUF`.
- **24 GB fit:** ✓ comfortably — Q4_K_M ≈ 14 GB (Q5/Q6 also fit).
- **Tool calling:** yes — **purpose-tuned for agentic coding / tool-use loops and
  codebase exploration**; a third lab (Mistral) for provenance diversity.

---

## UNRESTRICTED — alignment removed or absent, local

> The interesting contrast the thesis measures is **same class of model,
> alignment on vs. off**. The cleanest such contrast is an *abliterated twin* of a
> model already in the `OPEN_WEIGHT` bucket (`qwen3-30b-abliterated` vs.
> `qwen3-coder-30b`). WhiteRabbitNeo is kept as a separate, deliberately different
> question — "does a *security-domain* uncensored model win?" — and its extra
> domain fine-tune means it differs on **two** axes (alignment **and** domain
> tuning), which is noted so the run-for-record analysis doesn't read it as a pure
> alignment contrast.

### dolphin-mixtral-8x7b — Dolphin 2.7 Mixtral 8x7B
- **Developer:** Cognitive Computations (base: Mistral Mixtral-8x7B). **Arch:**
  MoE, 46.7B total / ~12.9B active. **Context:** 32K.
- **License:** Apache-2.0 (inherits Mixtral).
- **Weights / GGUF:** `cognitivecomputations/dolphin-2.7-mixtral-8x7b` · GGUF
  `TheBloke/dolphin-2.7-mixtral-8x7b-GGUF`.
- **24 GB fit:** ✗ **over profile** — Q4_K_M ≈ 26 GB; needs Q3_K_M (~20 GB) or
  partial CPU offload on a 24 GB card. Superseded by `dolphin-3.0-mistral-24b`
  below for the 4090 profile; kept for continuity with earlier runs.
- **Notes:** uncensored general-purpose fine-tune (the original registered
  unrestricted entry).

### whiterabbitneo-v3-7b — WhiteRabbitNeo V3 7B  *(new)*
- **Developer:** WhiteRabbitNeo / Kindo. **Arch:** dense, 7B. **Context:** 32K.
- **License:** **WhiteRabbitNeo Extension to Apache-2.0** — carries **usage
  restrictions** (track this in the replication snapshot the way the corpus
  manifest tracks per-binary license).
- **Weights / GGUF:** `WhiteRabbitNeo/WhiteRabbitNeo-V3-7B` · GGUF
  `bartowski/WhiteRabbitNeo_WhiteRabbitNeo-V3-7B-GGUF` · also
  `mradermacher/WhiteRabbitNeo-V3-7B-GGUF` (and `-i1-GGUF` imatrix builds).
- **24 GB fit:** ✓ trivially — Q4_K_M ≈ 5 GB (run a high quant, e.g. Q6_K/Q8_0).
- **Role:** the only model here **purpose-built for offensive/defensive security
  (DevSecOps)**, including exploit development — most **on-domain** for ROP.
- **Confound to document:** security-domain fine-tune → differs from an aligned
  sibling on alignment **and** domain, not alignment alone.
- **Alternatives (same cell):**
  `WhiteRabbitNeo/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B` (explicit Qwen2.5-Coder-7B
  base → strongest tool-calling lineage; GGUF
  `bartowski/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B-GGUF`) and the larger
  `WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5` (DeepSeek-Coder-33B base, Q4_K_M
  ≈ 19 GB, DeepSeek-Coder + WRN license restrictions).

### qwen3-30b-abliterated — Qwen3-30B-A3B (abliterated)  *(new)*
- **Developer:** base Alibaba (Qwen); **abliteration** by huihui-ai. **Arch:**
  MoE, 30.5B total / ~3.3B active. **Context:** 256K native (128K commonly used).
- **License:** Apache-2.0 (inherits base).
- **Weights / GGUF:** `huihui-ai/Qwen3-30B-A3B-abliterated` · GGUF
  `mradermacher/Qwen3-30B-A3B-abliterated-GGUF` (and `-i1-GGUF` imatrix).
- **24 GB fit:** ✓ — Q4_K_M ≈ 18–19 GB (same footprint/speed profile as
  `qwen3-coder-30b`).
- **Role:** the **cleanest alignment-off contrast** — same MoE architecture as the
  open-weight `qwen3-coder-30b`, with refusal behavior ablated. This is the ideal
  ADR 0005 "alignment on vs. off" cell.
- **Preferred variant if available:** the abliterated **Coder** build
  (`huihui-ai/Qwen3-Coder-30B-A3B-Instruct-abliterated`, if published as GGUF)
  gives the *tightest* twin of `qwen3-coder-30b`; verify tool-calling survives
  abliteration before committing it (see caveat below).

### dolphin-3.0-mistral-24b — Dolphin 3.0 Mistral-24B  *(new)*
- **Developer:** Cognitive Computations / dphn (base: Mistral-Small-24B). **Arch:**
  dense, 24B. **Context:** 32K. ChatML template.
- **License:** Apache-2.0 (inherits Mistral-Small-24B).
- **Weights / GGUF:** `cognitivecomputations/Dolphin3.0-Mistral-24B` (mirror
  `dphn/Dolphin3.0-Mistral-24B`) · GGUF
  `bartowski/cognitivecomputations_Dolphin3.0-Mistral-24B-GGUF`.
- **24 GB fit:** ✓ comfortably — Q4_K_M ≈ 14 GB.
- **Role:** modern uncensored **general-purpose** fine-tune and the 24 GB-friendly
  successor to `dolphin-mixtral-8x7b`; supports function calling. Shares the
  Mistral-Small-24B base with `devstral-small`, giving a partial matched pairing.
  A reasoning variant (`Dolphin3.0-R1-Mistral-24B`) also exists if a
  chain-of-thought unrestricted cell is wanted later.

---

## Fitting 24 GB

Weight-file footprint at **Q4_K_M** (gpt-oss = native MXFP4); the KV cache and
context sit on top, so leave headroom.

| Model | Quant | Weights ≈ | Fits 24 GB? |
|---|---|---:|---|
| qwen3-coder-30b (MoE) | Q4_K_M | 18–19 GB | ✓ |
| qwen3-30b-abliterated (MoE) | Q4_K_M | 18–19 GB | ✓ |
| gpt-oss-20b (MoE) | MXFP4 | 12–14 GB | ✓ (roomy) |
| devstral-small | Q4_K_M | ~14 GB | ✓ |
| dolphin-3.0-mistral-24b | Q4_K_M | ~14 GB | ✓ |
| whiterabbitneo-v3-7b | Q6_K/Q8_0 | 6–8 GB | ✓ (roomy) |
| qwen2.5-coder-7b (smoke) | Q4_K_M | ~5 GB | ✓ (roomy) |
| qwen2.5-coder-32b | Q4_K_M | ~20 GB | ✓ tight |
| dolphin-mixtral-8x7b | Q4_K_M | ~26 GB | ✗ (use Q3 / offload) |
| llama-3.3-70b | Q4_K_M | ~42 GB | ✗ (cloud/large-host) |

**LM Studio settings that buy context room on 24 GB:** enable **Flash Attention**
and set **KV-cache quantization to Q8** — on a 24 GB budget that's roughly the
difference between ~8K and ~32K+ usable context, which matters because gadget
dumps and disassembly get large.

## Tool-calling validation (do this before any run-for-record)

The agent loop ([`agent/graph.py`](../agent/graph.py)) is **tool-call driven** via
MCP. Abliteration and uncensoring can degrade instruction-following and tool-JSON
formatting, and a model that won't emit valid tool calls is useless to the harness
regardless of raw capability. **Before adding any local model to the run matrix,
smoke-test it through the LangGraph loop** (the `qwen2.5-coder-7b` slot exists for
exactly this transport check) and confirm it round-trips at least one MCP tool
call. This is where the `UNRESTRICTED` models are most likely to fail silently.

## Reproducibility / provenance

These community GGUF repos churn (re-quantized, renamed, deleted). For the
**replication snapshot** (Step 8), pin **more than the repo name**:

- the exact GGUF **file** used (e.g. `...-Q4_K_M.gguf`) and its **sha256**,
- the **quantization** and the LM Studio / llama.cpp build version,
- the model **license** (note the WhiteRabbitNeo and DeepSeek-Coder restrictions),
- the `BackendCategory` assigned here (the a-priori classification travels with
  the data, per ADR 0005).

This mirrors how [`../corpus/manifest.yaml`](../corpus/manifest.yaml) pins each
binary by sha256 + license, so a later researcher classifies and reproduces the
exact model the same way.
