# Contributing

This repo is the experimental apparatus for a SANS.edu thesis. Contributions
are welcome but the bar is calibrated for *reproducibility of published
results*, not feature velocity.

## Setup

```bash
./scripts/bootstrap.sh
./scripts/doctor.sh    # sanity-check the environment
```

## Before opening a PR

```bash
make format       # auto-format with ruff
make lint         # ruff check
make test         # pytest + coverage
```

CI runs the same commands on every push.

## What to change with care

These touch the data layer and need extra review:

- `harness/record.py` — the run-record schema. Changes are versioning events;
  bump `schema_version` and add a migration note in `docs/`.
- `analysis/aggregate.py` — the collapsing rule. Changing this changes what
  every notebook reports.
- `validator/classifier.py` — the single source of truth for which outcome a
  run gets. Add a unit test for any new branch.

## ADRs

Architectural decisions get a numbered file in `docs/adr/`. Don't edit a past
ADR; supersede it with a new one and link both ways. The current set:

- `0001-use-langgraph.md`
- `0002-validator-boundary.md`

## Style notes

- Type-annotate everything that crosses a module boundary.
- Use `StrEnum` rather than string literals for outcome / failure-mode / strategy.
- Tests live in `tests/` and follow the layout `tests/test_<module>.py`.
- Avoid one-letter variable names except for canonical math (`k`, `n`, `i`, `j`).
