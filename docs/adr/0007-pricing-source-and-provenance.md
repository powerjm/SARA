# ADR 0007 — Model pricing is a single versioned file, recorded per run

Status: Accepted (decided 2026-06-25; Step 8 run-for-record hardening)

## Context

Every `RunRecord` carries a `CostRecord` (`harness/record.py`), and the thesis
reports per-cell cost. Cost is computed inside each backend from a per-million-token
price table. As built (Steps 5–7) that table was **hard-coded and duplicated in
three places**:

- each provider backend's `PRICING` dict (`backends/anthropic_backend.py`,
  `openai_backend.py`, `google_backend.py`),
- the registry, which re-copied the rates as tuples to power the `--dry-run`
  estimate (`backends/registry.py::_register_defaults`),
- the synthetic dataset generator (`analysis/synthetic.py`).

Two problems followed. **(1) Drift / correctness:** the three copies could
diverge, and one had — `claude-opus-4-7` was pinned at `$15/$75` per Mtok while
the actual list price is `$5/$25`, so every recorded Opus cost was ~3× too high.
The only safeguard was a "verify before each run" code comment. **(2) No
provenance:** `CostRecord` stored only the final `usd`. The *rates* that produced
it were nowhere in the record, so a recorded cost could not be audited or
recomputed later — a real defect for an instrument whose purpose is reproducible
published numbers.

Two design questions had to be answered before fixing this:

- **Where do prices come from** — a pinned, versioned file, or fetched live at
  run time?
- **How is the price that produced a cost preserved** — with the run, or out of
  band?

## Decision

**1. One versioned source of truth, refreshed deliberately — never fetched at
run time.** Prices live in `backends/pricing.yaml` (USD per Mtok per model, each
with an `as_of` date and a `source` URL, under a top-level `pricing_version`).
`backends/pricing.py` is the only loader; the backends, the registry estimator,
and the synthetic generator all read through it, so a rate exists in exactly one
place. `scripts/refresh_pricing.py` updates the file as a reviewed, committed
step (`--check` flags staleness, `--bump` stamps the version); there is no
network call in the run path.

**2. Embed a pricing snapshot in every record (schema v1 → v2).**
`CostRecord.pricing` is a new optional `PricingSnapshot` (the two rates +
`pricing_version` + `as_of`). `Backend.pricing_snapshot()` supplies it; the
harness records it once per run (`agent/graph.py::build_run_record`). A run is
then self-describing: `tokens × recorded rates == recorded usd`, verifiable from
the record alone. `schema_version` accepts `"1"` and `"2"`; v1 records (which
predate the field) load with `cost.pricing is None`. See
`docs/SCHEMA_MIGRATIONS.md`.

Local/unpriced backends (LM Studio models, the scripted fake) have no entry in
`pricing.yaml`; their `CostRecord` keeps `usd=0.0` and `pricing=None`.

## Consequences

**Positive:**

- **One place to be right.** A price is defined once; the registry and the
  backends cannot disagree (a test asserts `registry.pricing(cell)` equals the
  central rate for that cell's model). The Opus error is corrected and pinned by
  a regression test.
- **Reproducible cost.** Each record states the rates it used, so any published
  cost number can be recomputed and audited years later — independent of what
  `pricing.yaml` says by then.
- **Reproducible runs.** Pinning (vs. live fetch) means re-running a stored
  experiment computes the same cost, with no network dependency in the run path
  — consistent with the offline/sandboxed ethos.
- **A pre-run gate.** `sara batch --dry-run` and `refresh_pricing.py --check`
  surface the pricing version/age so a run for record does not silently use
  stale rates.

**Negative:**

- **Manual refresh.** Prices can go stale between refreshes. Mitigation: the
  `as_of`/`pricing_version` metadata + the freshness warning make staleness
  visible rather than silent.
- **A schema-versioning event.** Adding `cost.pricing` bumps `schema_version` and
  obliges every serialiser/deserialiser to handle both versions. Mitigation: the
  field is optional and readers accept v1, so existing run dirs keep loading.

## Alternatives considered

- **Live pricing fetch at run time.** Rejected. It breaks reproducibility (the
  same stored run would recompute to a different cost as prices change), adds a
  network dependency to the run path, and there is no stable machine-readable
  pricing API across the three providers — it would mean scraping. "Current"
  pricing is the wrong goal for a reproducibility instrument; *recorded* pricing
  is the right one.
- **Keep records lean; write a per-batch pricing manifest referenced by
  version.** Rejected as the primary mechanism. It makes a record non-self-
  contained (auditing one record requires also locating its manifest). Embedding
  the snapshot is a few bytes per record and removes that coupling. (`pricing.yaml`
  is itself a committed, versioned manifest, so the provenance trail still exists
  out of band as well.)
- **A single central Python dict, hand-edited (no file/metadata).** Rejected. It
  removes duplication but carries no `as_of`/version/source provenance and no
  refresh/freshness tooling — the staleness problem that produced the Opus error
  would remain unaddressed.
