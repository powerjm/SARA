# Schema migrations — `harness/record.py`

`RunRecord.schema_version` is the contract version for stored run records. The
schema is the canonical data structure of the experiment (see
`docs/ARCHITECTURE.md`); any field change is a versioning event that bumps this
number and is recorded here. Readers accept every version listed below, so run
directories produced by older versions keep loading.

## v1 → v2 — pricing snapshot in `CostRecord` (2026-06-25)

**What changed.** `CostRecord` gained an optional `pricing` field, a
`PricingSnapshot` recording the per-million-token rates that produced `usd`
(`prompt_per_mtok`, `completion_per_mtok`, `pricing_version`, `as_of`). This
makes a recorded cost auditable and recomputable from the record alone
(`tokens × rates == usd`). See ADR 0007.

**Why.** Prices were previously hard-coded in three places and the record stored
only the final `usd`, so the rates behind a cost were unrecoverable. Pricing is
now centralized in `backends/pricing.yaml` and the rates used are stamped into
each run.

**Compatibility.**

- `schema_version` is `Literal["1", "2"]`, default `"2"`. New records are
  written as `"2"`; v1 records still validate.
- The new field is optional and defaults to `None`. A v1 record (no
  `cost.pricing` key) deserializes unchanged, with `cost.pricing is None`.
- Local/unpriced backends (LM Studio models, the scripted fake) also record
  `cost.pricing is None` — `None` means "no per-token price", whether the record
  is legacy or local.

**Reader guidance.** Treat `cost.pricing is None` as "rates not recorded" (legacy
or local) and fall back to whatever you did before v2 — e.g. an external price
table — only when you must. Aggregation/statistics code keyed on `cost.usd` is
unaffected: `usd` is unchanged in meaning and position.

**No back-fill.** Existing v1 records are left as-is (they remain valid). If a
historical cost must be re-derived, use the `pricing_version`/`as_of` in a
contemporaneous `backends/pricing.yaml` revision.
