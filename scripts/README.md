# scripts/

Developer helpers. Not used at experiment runtime — those tools live under `harness/cli.py`.

| Script | Purpose |
|--------|---------|
| `bootstrap.sh` | Create the venv, install pinned deps, install pre-commit hooks, seed `.env`. |
| `doctor.sh`    | Print a readiness report for the apparatus. Run this first on a fresh machine. |
| `build_replication_snapshot.sh` | Build the reproducibility bundle (`sara-snapshot-<commit>.tar.zst`). See [`docs/REPLICATION_SNAPSHOT.md`](../docs/REPLICATION_SNAPSHOT.md). |
| `verify_snapshot.sh` | Re-validate a snapshot: re-execute every stored payload and confirm each recorded outcome reproduces. |

Make them executable: `chmod +x scripts/*.sh`.
