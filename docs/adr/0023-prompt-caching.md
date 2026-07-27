# ADR 0023 — Prompt caching / KV-prefix reuse

Status: Accepted (Trial 3 — 2026-07-27)

Companion to ADR 0022 (context engineering). Stops the re-prefill / re-billing of the stable prefix
(system + tool schema) that every stateless provider otherwise pays on every reason turn.

## Context

Providers are stateless: the `tools` schema and system prompt **cannot** be omitted — they must be sent
each turn. SARA sends the whole (now curated, ADR 0019) tool schema and system prompt every REASON
turn, and Trial 2 used **no caching at all**: `backends/anthropic_backend.py` rebuilt `system` + `tools`
+ `messages` fresh each `chat()`, and the OpenAI / LM Studio backends likewise. The schema + system
prompt are large and byte-stable across a run — exactly the shape a prefix cache is built for.

## Decision

**Mark the stable prefix cacheable, and keep it byte-stable so the cache actually hits.**

1. **Anthropic — explicit `cache_control`.** `AnthropicBackend` marks the system prompt (as a single
   cached text block) and the **last** tool in the schema (the breakpoint caches every tool before it)
   with `cache_control: {"type": "ephemeral"}`. A cache hit re-bills that prefix at ~10%. Caching is a
   backend property (default on, `_prompt_cache`), not a per-run flag — it is always correct to cache a
   stable prefix. Cache-read/write counts come back in `resp.usage` and are surfaced via
   `ChatResponse.raw` for the preflight cache-hit-rate gate (Phase D).
2. **OpenAI — automatic prefix cache.** The real OpenAI API caches a ≥1024-token prefix automatically;
   it needs only a stable prefix, which the backend already provides (system first, then tools, then the
   message log) and which ADR 0022's compaction keeps byte-stable across turns. No explicit marking
   exists in the API; correctness is "don't perturb the prefix", which is now a tested property.
3. **LM Studio / llama.cpp — KV-cache prefix reuse.** A byte-stable prefix lets the server skip prefill
   for the unchanged prefix — pure speed, and the biggest relief for the slow/truncation-prone locals
   (the demand-side answer to the L4 throughput confound). Same requirement: a stable prefix.
4. **Byte-stability is the shared contract.** ADR 0022 keeps the prefix (system + task + pinned plan)
   stable and confines churn to the suffix, compacting in batches so the cache-miss reset is rare. That
   is what makes all three caches fire.

## Consequences

**Positive:**

- The large stable prefix (tool schema + system) is billed once and then re-read cheaply (Anthropic) or
  skipped in prefill (OpenAI auto / llama.cpp KV) every subsequent turn — a direct cut to the
  prompt-dominated cost, compounding with ADR 0022's compaction.
- Cross-run cache reuse of a **content-free** provider prefix is benign and accepted (it moves no
  information between runs, so it cannot break the paired-stats independence); a store shared across
  runs would be prohibited, but caching a stable system+tools prefix is not that (Trial 3 §1).
- The cache counters are measurable, so the preflight gate can prove the cache is actually firing before
  the run rather than assuming it.

**Negative / limitations (recorded honestly):**

- Anthropic's ephemeral cache has a short TTL; a slow reasoning turn between calls can let the prefix
  expire and force a full re-bill. This is a provider property, not something the harness controls.
- OpenAI/LM Studio caching is implicit — there is no request field asserting it, so the guarantee is
  only "the prefix is byte-stable", verified by test, not a provider ack.
- If ADR 0022's facts digest changes on a turn (a new batch of compaction), the portion of the prefix
  after the cached system+tools is invalidated for that turn; the batched compaction keeps this rare but
  not zero.

## Alternatives considered

- **No caching (Trial 2 status quo).** Rejected: it pays full prefill/billing for a large, unchanging
  prefix every turn — the exact cost this trial targets.
- **Cache the full message log, not just the prefix.** Rejected: the log's suffix churns every turn, so
  only the stable prefix is a reliable cache; ADR 0022 is what makes the prefix stable enough to cache.
- **A cross-run semantic cache of tool results.** Rejected: it would share information across runs and
  break McNemar/Friedman independence (Trial 3 §1). Only within-run state (ADR 0022) and content-free
  provider prefix reuse are allowed.

## Ethical scope

Unchanged. Educational/CTF targets only, proof-of-concept payloads only, one sandboxed execution point
(ADR 0002/0016). Caching changes only how the prompt prefix is billed/prefilled; it adds no capability,
no execution path, and no information-bearing cross-run state.
