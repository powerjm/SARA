"""
Build corpus binaries from source (the cb-multios path).

`fetch.py` downloads a prebuilt artifact and SHA256-checks it. That does not work
for the DARPA CGC binaries: the original CBs target DECREE (they will not run in
the validator sandbox), so we use the Trail of Bits Linux port,
``trailofbits/cb-multios`` (MIT), which re-implements the CGC syscalls on libc and
produces native Linux ELFs. Those are *built*, not downloaded, and cb-multios
*renames* each challenge directory to a descriptive name — so the original CGC id
(``CROMU_00004``) no longer matches a path.

This script bridges that gap. Given a cb-multios checkout it:

  1. resolves the renamed challenge directory by grepping the checkout for the
     original CGC id (which cb-multios preserves inside each challenge),
  2. locates the built (vulnerable, *not* ``_patched``) ELF,
  3. hashes it and either verifies it against the manifest pin or, with
     ``--update``, rewrites the pin in place (comment-preserving),
  4. installs it to ``corpus/binaries/<id>``.

It does **not** own cb-multios's CMake build — build the challenges first per the
cb-multios README (``./build.sh``), then point this at the checkout. Pass
``--from`` to skip resolution and install an explicit pre-built ELF.

The cb-multios build is not guaranteed byte-identical across toolchains, so the
pinned sha256 records *your* lab-host build (like the fixture's ``build.sh``);
re-pin deliberately with ``--update`` and commit the new hash.

Usage:
    # Build cb-multios first (per its README), then:
    python -m corpus.scripts.build --all --cb-multios ~/src/cb-multios
    python -m corpus.scripts.build --id cgc-cromu-00004 --cb-multios ~/src/cb-multios
    python -m corpus.scripts.build --id cgc-cromu-00004 --cb-multios ~/src/cb-multios --update
    python -m corpus.scripts.build --id cgc-cromu-00004 --from /path/to/built/Audio_Decoder
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

CORPUS_DIR = Path(__file__).resolve().parent.parent
MANIFEST = CORPUS_DIR / "manifest.yaml"
BINARIES_DIR = CORPUS_DIR / "binaries"

_ELF_MAGIC = b"\x7fELF"
_ZERO_SHA = "0" * 64


def cgc_id_for(entry: dict[str, Any]) -> str:
    """The original CGC id for an entry (the key cb-multios preserves internally).

    Prefers an explicit ``build.challenge`` override; otherwise derives it from
    the manifest id by stripping the ``cgc-`` prefix and upper-casing, e.g.
    ``cgc-cromu-00004`` -> ``CROMU_00004``.
    """
    build = entry.get("build")
    if isinstance(build, dict) and build.get("challenge"):
        return str(build["challenge"])
    bid = str(entry["id"])
    stem = bid[len("cgc-") :] if bid.startswith("cgc-") else bid
    return stem.replace("-", "_").upper()


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks (binaries can be large)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == _ELF_MAGIC
    except OSError:
        return False


def resolve_cb_dir(cb_root: Path, cgc_id: str) -> Path | None:
    """Find the (renamed) cb-multios challenge directory for an original CGC id.

    cb-multios drops the original id but keeps it inside the challenge (READMEs,
    sources, build metadata), so we look for the challenge directory under
    ``<cb_root>/challenges/`` that mentions ``cgc_id``. Returns the directory, or
    ``None`` if no single challenge references it.
    """
    challenges = cb_root / "challenges"
    if not challenges.is_dir():
        return None
    needle = cgc_id.encode()
    for child in sorted(p for p in challenges.iterdir() if p.is_dir()):
        # A directly-named dir still wins (some forks keep the original id).
        if child.name == cgc_id:
            return child
        for path in child.rglob("*"):
            if not path.is_file():
                continue
            try:
                if needle in path.read_bytes():
                    return child
            except OSError:
                continue
    return None


def locate_built_binary(cb_root: Path, challenge_dir: Path) -> Path | None:
    """Find the built, vulnerable ELF for a resolved challenge directory.

    cb-multios builds out-of-source (default ``<cb_root>/build/...``) and emits
    both the vulnerable binary (named after the challenge) and a ``*_patched``
    variant — we want the vulnerable one. Searches common build locations for an
    ELF named exactly after the challenge directory, preferring paths under a
    ``build`` tree and never matching ``*_patched``.
    """
    name = challenge_dir.name
    candidates: list[Path] = []
    search_roots = [cb_root / "build", cb_root / "build64", challenge_dir, cb_root]
    for root in search_roots:
        if not root.is_dir():
            continue
        for path in root.rglob(name):
            if path.is_file() and not path.name.endswith("_patched") and _is_elf(path):
                candidates.append(path)
    if not candidates:
        return None
    # Prefer a path that lives under a build directory (the freshly compiled ELF).
    candidates.sort(key=lambda p: (0 if "build" in p.parts else 1, len(p.parts)))
    return candidates[0]


def repin_manifest_text(text: str, entry_id: str, new_sha: str) -> str:
    """Return ``text`` with the sha256 of the ``entry_id`` block set to ``new_sha``.

    Comment-preserving: edits only the first ``sha256:`` line inside the entry's
    block (from its ``- id: <entry_id>`` line up to the next ``- id:`` or EOF), so
    the rest of the hand-maintained manifest is untouched. Raises if the entry or
    its sha256 line is not found.
    """
    lines = text.splitlines(keepends=True)
    id_re = re.compile(r"^(\s*)-\s+id:\s*([\"']?)" + re.escape(entry_id) + r"\2\s*$")
    start = next((i for i, ln in enumerate(lines) if id_re.match(ln)), None)
    if start is None:
        raise KeyError(f"entry id {entry_id!r} not found in manifest")
    next_id = re.compile(r"^\s*-\s+id:\s")
    end = next((i for i in range(start + 1, len(lines)) if next_id.match(lines[i])), len(lines))
    sha_re = re.compile(r"^(?P<pre>\s*sha256:\s*)(?P<q>[\"']?)[0-9a-fA-F]*(?P=q)(?P<post>\s*)$")
    for i in range(start, end):
        match = sha_re.match(lines[i])
        if match:
            lines[i] = f'{match["pre"]}"{new_sha}"{match["post"] or chr(10)}'
            return "".join(lines)
    raise KeyError(f"no sha256: line found in the {entry_id!r} block")


def _install(elf: Path, binary_id: str) -> Path:
    """Copy a built ELF into the corpus binaries dir as ``<binary_id>``."""
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    dest = BINARIES_DIR / binary_id
    shutil.copy(elf, dest)
    dest.chmod(0o755)  # an executable; the validator re-chmods 0o555 in-sandbox
    return dest


def build_one(
    entry: dict[str, Any],
    *,
    cb_root: Path | None,
    from_path: Path | None,
    update: bool,
) -> bool:
    """Resolve, hash, pin/verify and install a single manifest entry's binary."""
    bid = str(entry["id"])

    if from_path is not None:
        elf = from_path
        if not _is_elf(elf):
            print(f"  FAIL {bid}: --from {elf} is not an ELF")
            return False
    else:
        if cb_root is None:
            print(f"  SKIP {bid}: need --cb-multios <checkout> or --from <elf>")
            return False
        cgc_id = cgc_id_for(entry)
        challenge_dir = resolve_cb_dir(cb_root, cgc_id)
        if challenge_dir is None:
            print(f"  FAIL {bid}: no cb-multios challenge references {cgc_id}")
            return False
        elf = locate_built_binary(cb_root, challenge_dir) or Path()
        if not elf or not elf.is_file():
            print(
                f"  FAIL {bid}: {cgc_id} -> {challenge_dir.name}, but no built ELF found. "
                "Build cb-multios first (its ./build.sh), then retry."
            )
            return False

    actual = sha256_of(elf)
    expected = str(entry.get("sha256", ""))

    if update or expected == _ZERO_SHA:
        new_text = repin_manifest_text(MANIFEST.read_text(encoding="utf-8"), bid, actual)
        MANIFEST.write_text(new_text, encoding="utf-8")
        dest = _install(elf, bid)
        verb = "repinned" if update else "pinned"
        print(f"  OK   {bid}: {verb} {actual} <- {elf}")
        print(f"       installed -> {dest}")
        return True

    if actual != expected:
        print(f"  FAIL {bid}: sha256 mismatch (expected {expected}, got {actual})")
        print(f"       {elf}; re-pin deliberately with --update if the toolchain changed")
        return False

    dest = _install(elf, bid)
    print(f"  OK   {bid}: {actual} matches the pin; installed -> {dest}")
    return True


def main(argv: list[str]) -> int:
    only: str | None = None
    cb_root: Path | None = None
    from_path: Path | None = None
    update = "--update" in argv

    if "--id" in argv:
        only = argv[argv.index("--id") + 1]
    if "--cb-multios" in argv:
        cb_root = Path(argv[argv.index("--cb-multios") + 1]).expanduser()
    if "--from" in argv:
        from_path = Path(argv[argv.index("--from") + 1]).expanduser()

    if from_path is not None and only is None:
        print("error: --from requires --id <binary_id>", file=sys.stderr)
        return 2

    with MANIFEST.open(encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh)

    ok = True
    matched = False
    for entry in manifest["binaries"]:
        if only and entry["id"] != only:
            continue
        matched = True
        if not str(entry.get("source_url", "")).startswith("git+") and from_path is None:
            print(f"  SKIP {entry['id']}: not a build-from-source (git+) entry; use fetch.py")
            continue
        if not build_one(entry, cb_root=cb_root, from_path=from_path, update=update):
            ok = False

    if only and not matched:
        print(f"error: unknown --id {only!r}", file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
