"""
Verify corpus-truth.

For each binary in the manifest, run the documented exploit and confirm the
success marker appears on stdout. This is the gate that locks the corpus
before any agent runs happen.

Implementation: thin wrapper around the validator. The "documented exploit"
for each binary is stored alongside it as a small Python script under
`corpus/exploits/<id>.py` (Phase 4 deliverable; the file does not yet exist).

Phase 4 stub.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CORPUS_DIR = Path(__file__).resolve().parent.parent
MANIFEST = CORPUS_DIR / "manifest.yaml"
EXPLOITS_DIR = CORPUS_DIR / "exploits"
BINARIES_DIR = CORPUS_DIR / "binaries"


def main(argv: list[str]) -> int:
    only: str | None = None
    if "--id" in argv:
        idx = argv.index("--id")
        only = argv[idx + 1]

    with MANIFEST.open() as f:
        manifest = yaml.safe_load(f)

    print("Phase 4 stub. Implementation steps:")
    print("  1. Load corpus/manifest.yaml.")
    print("  2. For each binary (or just --id if given): run corpus/exploits/<id>.py")
    print("     in the validator sandbox.")
    print("  3. Confirm the success_marker appears on stdout.")
    print("  4. Print a pass/fail table and return non-zero if any failed.")
    print()
    print(f"  Manifest has {len(manifest['binaries'])} entries:")
    for entry in manifest["binaries"]:
        if only and entry["id"] != only:
            continue
        exploit = EXPLOITS_DIR / f"{entry['id']}.py"
        bin_path = BINARIES_DIR / entry["id"]
        status = "ready" if (exploit.exists() and bin_path.exists()) else "missing files"
        print(f"    - {entry['id']:30s}  {status}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
