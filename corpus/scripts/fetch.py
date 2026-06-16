"""
Fetch corpus binaries based on manifest.yaml.

Each entry's source_url is fetched, SHA256-verified, and saved to
corpus/binaries/<id>. Mismatch is fatal.

Usage:
    python -m corpus.scripts.fetch                  # fetch all
    python -m corpus.scripts.fetch --id sample-overflow
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

CORPUS_DIR = Path(__file__).resolve().parent.parent
MANIFEST = CORPUS_DIR / "manifest.yaml"
BINARIES_DIR = CORPUS_DIR / "binaries"


def fetch_one(entry: dict[str, Any]) -> bool:
    bid = entry["id"]
    dest = BINARIES_DIR / bid
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    url = entry["source_url"]
    if url.startswith("TODO"):
        print(f"  SKIP {bid}: source_url is a placeholder")
        return False
    if url.startswith("git+"):
        print(f"  SKIP {bid}: build-from-source (git+); use `corpus.scripts.build`")
        return False

    expected = entry["sha256"]
    if expected == "0" * 64:
        print(f"  SKIP {bid}: sha256 is a placeholder")
        return False

    print(f"  GET  {url} -> {dest}")
    with urllib.request.urlopen(url) as resp:  # noqa: S310  # corpus URLs are reviewed
        data = resp.read()

    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        print(f"  FAIL {bid}: sha256 mismatch (expected {expected}, got {actual})")
        return False

    dest.write_bytes(data)
    dest.chmod(0o644)
    print(f"  OK   {bid}")
    return True


def main(argv: list[str]) -> int:
    only: str | None = None
    if "--id" in argv:
        idx = argv.index("--id")
        only = argv[idx + 1]

    with MANIFEST.open() as f:
        manifest = yaml.safe_load(f)

    ok = True
    for entry in manifest["binaries"]:
        if only and entry["id"] != only:
            continue
        if not fetch_one(entry):
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
