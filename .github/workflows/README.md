# GitHub Actions workflows — disabled

The workflow files in this directory carry a **`.disabled`** suffix on purpose.
GitHub only loads `*.yml` / `*.yaml` files here, so nothing in this directory
runs.

- `ci.yml.disabled` — lint / mypy / pytest / sandbox-image build.
- `codeql.yml.disabled` — CodeQL static analysis.

## Why

Both workflows called third-party GitHub Actions pinned to **mutable tags**
(`actions/checkout@v4`, `docker/build-push-action@v6`,
`github/codeql-action@v3`, …). A mutable tag can be repointed to malicious code
by a compromise of the action's repo or a maintainer account — the supply-chain
failure mode behind the recent wave of Actions tag-hijacks. On a **public** repo
those workflows run on pull-request events too, widening the blast radius. For a
feature-complete thesis instrument headed for archival, the cost/benefit does
not favour keeping hosted CI on.

Full rationale and the re-enable procedure: **`docs/adr/0006-disable-ci-workflows-for-public-release.md`**.

## What replaces them

Quality enforcement is local, running no third-party-hosted code on push:

```bash
make format && make lint && make test   # before every commit
```

plus the `pre-commit` hooks (local-only) and the Step 8 smoke test
(`tests/test_smoke_e2e.py`) as part of the run-for-record procedure.

## Re-enabling

Do **not** simply rename these back. Per ADR 0006: rename to `*.yml`, then pin
every third-party action to a full commit SHA (not a tag) and add a pin-updater,
before layering any merge gates on top.
