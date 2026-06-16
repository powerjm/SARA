# scripts/

Developer helpers. Not used at experiment runtime — those tools live under `harness/cli.py`.

| Script | Purpose |
|--------|---------|
| `bootstrap.sh` | Create the venv, install pinned deps, install pre-commit hooks, seed `.env`. |
| `doctor.sh`    | Print a readiness report for the apparatus. Run this first on a fresh machine. |

Make both executable: `chmod +x scripts/*.sh`.
