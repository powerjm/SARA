# ADR 0005 — Open-weight vs unrestricted is decided by safety-alignment status

Status: Accepted (decided 2026-06-15; the boundary the Step 7 backends register against)

## Context

The experiment treats the **backend category** as a factor: every `RunRecord`
carries a `BackendCategory` (`harness/record.py`), and the thesis compares
behaviour across categories. The enum has three values:

- `PREMIUM` — hosted frontier models reached through a vendor API (Anthropic,
  OpenAI, Google). Unambiguous, already implemented (`backends/anthropic_backend.py`
  and the Step 7 OpenAI/Google backends all set `category = BackendCategory.PREMIUM`).
- `OPEN_WEIGHT`
- `UNRESTRICTED`

`OPEN_WEIGHT` and `UNRESTRICTED` models are both served **locally through the
same LM Studio endpoint** in the local run option, so the transport does not
distinguish them — `backends/lmstudio_backend.py` takes `category` as a
constructor argument precisely because one endpoint serves both. The open
question (flagged on Step 7 of `docs/SARA_DEVELOPMENT_HISTORY.md`): **what is the
boundary between `OPEN_WEIGHT` and `UNRESTRICTED`?**

The category must be:

- **A priori and stable** — it is an independent variable of the experiment, so
  it has to be fixed *before* a run, not derived from that run's behaviour.
- **Reproducible** — another researcher must classify the same model the same way
  from the replication snapshot.

## Decision

The boundary is the model's **safety-alignment status**:

- **`OPEN_WEIGHT`** — a model whose weights are publicly downloadable **and whose
  safety/alignment tuning is intact**, as released by the originating lab. These
  are the standard instruct/chat releases: e.g. Llama, Qwen, Mistral instruct
  models in their official form.
- **`UNRESTRICTED`** — a model whose safety alignment has been **removed or was
  never present**: abliterated / "uncensored" community fine-tunes that strip
  refusal behaviour, and base/foundation models released without
  instruction+safety tuning.

The distinguishing axis is *alignment*, not licence, not host, not vendor. The
classification is **declared a priori per model** at registration time — each
backend's `BackendCategory` is fixed in `backends/registry.py` (the single source
of truth for known backends; for LM Studio-served models the category is the
value passed to `register(...)`/the constructor). `PREMIUM` is unchanged: hosted
frontier models behind a vendor API.

## Consequences

**Positive:**

- **Measures the variable the thesis cares about.** The interesting question is
  whether *removing safety alignment* changes an agent's willingness and ability
  to build ROP chains. Splitting on alignment status puts that contrast directly
  on the category axis: `OPEN_WEIGHT` vs `UNRESTRICTED` is "same class of model,
  alignment on vs off."
- **A priori and non-circular.** Refusal is an *outcome* we measure
  (`Backend.detect_refusal`, ADR-adjacent decision #2). Categorising by alignment
  status — a property of the model's provenance, set before the run — keeps the
  independent variable (category) separate from the dependent variable (refusal
  rate). Defining the category *by* measured refusal would be circular.
- **Reproducible.** The category is recorded per backend in the registry and in
  the replication snapshot, so the classification travels with the data.

**Negative:**

- **Relies on a provenance claim.** "Alignment intact" is a statement about how
  the model was released, which for some community fine-tunes is a judgement
  call. Mitigation: the category is set explicitly at registration and the model
  identity (and source) is recorded, so a reviewer can audit each assignment.
- **Binary, not graded.** Partial or weak alignment is forced into one bucket;
  the scheme does not express "lightly aligned." Acceptable for the thesis's
  three-way design; a finer scale would be a schema change (and a new ADR).

## Alternatives considered

- **Empirical refusal rate (measure, then bucket).** Rejected. It would classify
  a model by its refusal rate on a probe set, above/below a threshold. This is
  circular — refusal is exactly the behaviour the experiment measures, so the
  category would be derived from the outcome — and it needs an arbitrary
  threshold plus a maintained probe suite. The category must be fixed before the
  run, not computed from it.
- **Licence / provenance (who shipped it, under what terms).** Rejected. Licence
  is orthogonal to behaviour: a permissively-licensed model can be fully aligned,
  and an "uncensored" fine-tune can carry the same base licence as its aligned
  parent. Splitting on licence would not isolate the alignment contrast the
  thesis is about.
