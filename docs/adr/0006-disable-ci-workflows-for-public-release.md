# ADR 0006 — GitHub Actions workflows are disabled for the public release

Status: Accepted (decided 2026-06-25; supersedes the Step 8 "CI gates required for merge" criterion)

## Context

The repository is being prepared for public release alongside the thesis. Two
GitHub Actions workflows existed:

- `.github/workflows/ci.yml` — lint / mypy / pytest / sandbox-image build,
  calling `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`,
  `docker/setup-buildx-action`, and `docker/build-push-action`.
- `.github/workflows/codeql.yml` — CodeQL analysis, calling `actions/checkout`
  and `github/codeql-action/{init,analyze}`.

Every one of those third-party actions was pinned to a **mutable tag** (`@v4`,
`@v3`, `@v6`), not a commit SHA. A mutable tag is repointed by the action's
owner at any time, so a compromise of any of those repositories (or of a
maintainer account) would execute attacker-controlled code in this repo's CI
runner. This is the failure mode behind the wave of GitHub Actions
supply-chain compromises in circulation (tag-hijack of widely-used actions). On
a **public** repository the blast radius is larger: workflow runs are triggered
by events including pull requests, so the exposure is not limited to the
maintainer's own pushes.

The original Step 8 plan (`docs/SARA_DEVELOPMENT_HISTORY.md`) called for
*hardening* CI into required merge gates (coverage ≥85%, mypy strict,
`pip-audit`, CodeQL ≥ medium). That goal is in direct tension with the release
posture: keeping the workflows means keeping the third-party-action exposure.

This is a research instrument, not a continuously-developed product. The thesis
results depend on a pinned, recorded environment and on the local quality gates,
**not** on hosted CI. The cost/benefit of running third-party actions on a
public repo, for a project that is feature-complete and headed for archival,
does not favour keeping them on.

## Decision

**Disable the GitHub Actions workflows for the public release.** Both workflow
files are renamed with a `.disabled` suffix so GitHub no longer parses or runs
them (it only loads `*.yml` / `*.yaml` under `.github/workflows/`). Nothing in
this repository invokes a third-party GitHub Action.

Quality enforcement moves entirely to the **local / lab-host** toolchain, which
runs no third-party-hosted code on push:

- `make format && make lint && make test` before every commit (the working
  agreement, unchanged).
- The `pre-commit` hooks (ruff, whitespace/format fixers). These pull pinned
  third-party hook *repos* but execute **locally on the developer's machine**,
  never in a hosted runner triggered by repository events — a materially smaller
  exposure, and out of scope for this decision.
- The Step 8 smoke test (`tests/test_smoke_e2e.py`) is run on the lab host as
  part of the run-for-record procedure, not in hosted CI.

This **supersedes** the Step 8 done-when item "coverage/mypy/pip-audit/CodeQL
gates are required for merge." The gates still exist as local `make` targets and
as the documented pre-run procedure; they are no longer enforced by hosted CI.

## Consequences

**Positive:**

- No third-party GitHub Action runs on any repository event. The mutable-tag
  supply-chain exposure is removed outright rather than mitigated.
- Appropriate to a public, archival research repo: a forked PR cannot trigger a
  workflow run here at all.
- Fully reversible. The workflow content is preserved verbatim in the
  `.disabled` files; re-enabling is a rename plus the pinning work below.

**Negative:**

- No automated checks on push/PR. Contributors must run `make format && make
  lint && make test` locally; reviewers cannot rely on a green check. Mitigated
  by `CONTRIBUTING.md`, the pre-commit hooks, and the small contributor surface
  of a thesis instrument.
- The "CI gates required for merge" Step 8 criterion is dropped. The
  *replication snapshot* (ADR-adjacent, `docs/REPLICATION_SNAPSHOT.md`) and the
  local gates carry the reproducibility burden instead.

## Re-enabling later (out of scope now, recorded so it isn't lost)

If hosted CI is wanted again (e.g. the repo resumes active development), re-enable
**only** after removing the exposure this ADR is about:

1. Rename `*.yml.disabled` back to `*.yml`.
2. Pin **every** third-party action to a full 40-char commit SHA (not a tag),
   e.g. `actions/checkout@<sha>  # v4.2.2`, and adopt a pin-updater
   (Dependabot/Renovate) so the SHAs are reviewed when bumped.
3. Keep `permissions:` least-privilege (the existing `contents: read` default is
   correct; CodeQL additionally needs `security-events: write`).
4. Only then layer the Step 8 gates (coverage threshold, mypy strict,
   `pip-audit`, CodeQL severity) on top.

## Alternatives considered

- **Pin all actions to SHAs and keep the gates (the original Step 8 plan).**
  Rejected for the public-release window: it reduces but does not eliminate the
  exposure (a SHA-pinned action can still be malicious if the pinned commit is),
  and it carries ongoing pin-maintenance cost for a project that is
  feature-complete. Recorded above as the re-enable path if active development
  resumes.
- **Keep only a minimal pytest workflow using no third-party actions.**
  Rejected: a useful run still needs at least `actions/checkout`, so "no
  third-party actions" is not achievable while keeping any workflow. Half-measure
  with most of the maintenance cost and residual exposure.
- **Delete the workflow files entirely.** Rejected: renaming to `.disabled`
  preserves the exact configuration for review and for the re-enable path, and
  makes the disablement legible to a reader of the public repo. Deletion would
  discard that record.
