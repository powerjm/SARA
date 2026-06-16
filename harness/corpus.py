"""
Corpus resolution.

Turns a ``binary_id`` (the foreign key used everywhere in the experiment) into a
concrete :class:`BinarySpec`: the on-disk binary, its static context, the success
marker, and the documented-chain fingerprint the validator uses to decide
KNOWN_REDISCOVERY. The single source of truth is ``corpus/manifest.yaml`` (see
``corpus/README.md``); the binaries themselves are gitignored and live under
``corpus/binaries/``.

Both the manifest and the binaries directory can be redirected with environment
variables (``SARA_CORPUS_MANIFEST`` / ``SARA_CORPUS_BINARIES_DIR``) so the same
code resolves a binary on a laptop, on the cloud VM, or against a throwaway
fixture corpus in the test suite — only the paths differ, never the logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.state import BinaryContext
from validator.runner import chain_fingerprint

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_MANIFEST = _REPO_ROOT / "corpus" / "manifest.yaml"
_DEFAULT_BINARIES_DIR = _REPO_ROOT / "corpus" / "binaries"
_DEFAULT_EXPLOITS_DIR = _REPO_ROOT / "corpus" / "exploits"


class CorpusError(RuntimeError):
    """Raised when a binary cannot be resolved from the manifest."""


@dataclass(frozen=True)
class BinarySpec:
    """Everything a run needs to know about a corpus binary."""

    binary_id: str
    binary_path: Path
    architecture: str
    protections: list[str]
    success_marker: str
    documented_gadget_addresses: list[int]
    documented_chain_fingerprint: str | None
    difficulty_tier: int | None = None
    notes: str = ""

    def to_context(self) -> BinaryContext:
        """The static per-binary context the agent graph ingests."""
        return BinaryContext(
            binary_id=self.binary_id,
            binary_path=self.binary_path,
            architecture=self.architecture,
            protections=list(self.protections),
            notes=self.notes,
        )


def manifest_path() -> Path:
    """The manifest path, honoring ``SARA_CORPUS_MANIFEST``."""
    override = os.environ.get("SARA_CORPUS_MANIFEST")
    return Path(override) if override else _DEFAULT_MANIFEST


def binaries_dir() -> Path:
    """The binaries directory, honoring ``SARA_CORPUS_BINARIES_DIR``."""
    override = os.environ.get("SARA_CORPUS_BINARIES_DIR")
    return Path(override) if override else _DEFAULT_BINARIES_DIR


def exploits_dir() -> Path:
    """The documented-exploits directory, honoring ``SARA_CORPUS_EXPLOITS_DIR``."""
    override = os.environ.get("SARA_CORPUS_EXPLOITS_DIR")
    return Path(override) if override else _DEFAULT_EXPLOITS_DIR


def load_manifest(path: Path | None = None) -> list[dict[str, Any]]:
    """Load and return the manifest's ``binaries`` list."""
    path = path or manifest_path()
    if not path.is_file():
        raise CorpusError(f"corpus manifest not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    entries = data.get("binaries")
    if not isinstance(entries, list):
        raise CorpusError(f"manifest {path} has no 'binaries' list")
    return entries


def find_entry(binary_id: str, path: Path | None = None) -> dict[str, Any]:
    """Return the raw manifest entry for ``binary_id`` (raises if absent)."""
    for entry in load_manifest(path):
        if entry.get("id") == binary_id:
            return entry
    known = sorted(str(e.get("id")) for e in load_manifest(path))
    raise CorpusError(f"unknown binary_id {binary_id!r}. Known: {known}")


def _parse_addresses(raw: Any) -> list[int]:
    """Coerce a manifest ``documented_gadget_addresses`` list into ints."""
    if not raw:
        return []
    out: list[int] = []
    for item in raw:
        out.append(int(str(item), 16) if isinstance(item, str) else int(item))
    return out


def resolve_binary(
    binary_id: str,
    *,
    manifest: Path | None = None,
    binaries: Path | None = None,
    require_file: bool = True,
) -> BinarySpec:
    """Resolve ``binary_id`` to a :class:`BinarySpec`.

    The binary file is looked up at ``<binaries_dir>/<binary_id>``. When
    ``require_file`` is set (the default for a real run) a missing file raises;
    callers that only need metadata (e.g. a dry-run cost estimate) pass
    ``require_file=False``.
    """
    entry = find_entry(binary_id, manifest)
    bins = binaries or binaries_dir()
    binary_path = bins / binary_id

    if require_file and not binary_path.is_file():
        raise CorpusError(
            f"binary file for {binary_id!r} not found at {binary_path}. "
            "Fetch it with `python -m corpus.scripts.fetch --id "
            f"{binary_id}` or set SARA_CORPUS_BINARIES_DIR."
        )

    addresses = _parse_addresses(entry.get("documented_gadget_addresses"))
    fingerprint = chain_fingerprint(addresses) if addresses else None

    tier = entry.get("difficulty_tier")
    return BinarySpec(
        binary_id=binary_id,
        binary_path=binary_path,
        architecture=str(entry.get("architecture", "unknown")),
        protections=list(entry.get("protections") or []),
        success_marker=str(entry.get("success_marker", "")),
        documented_gadget_addresses=addresses,
        documented_chain_fingerprint=fingerprint,
        difficulty_tier=int(tier) if tier is not None else None,
        notes=str(entry.get("notes", "")).strip(),
    )


__all__ = [
    "BinarySpec",
    "CorpusError",
    "binaries_dir",
    "exploits_dir",
    "find_entry",
    "load_manifest",
    "manifest_path",
    "resolve_binary",
]
