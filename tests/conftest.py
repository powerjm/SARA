"""pytest configuration shared by the test suite."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

# Mark the process as a pytest run *before* any project import, so the backend
# registry only exposes the test-only "fake" backend under test.
os.environ.setdefault("PYTEST_RUNNING", "1")

# Make the project root and the tests dir importable so tests can do
# `from harness import ...` and `from fakes.backend import ...` without an
# editable install (and so the registry can resolve `fakes` under PYTEST_RUNNING).
_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
for _path in (_PROJECT_ROOT, _TESTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_FIXTURES = _TESTS_DIR / "fixtures"


def ropgadget_on_path() -> bool:
    """True when the ROPgadget CLI is resolvable on $PATH."""
    return shutil.which("ROPgadget") is not None


def radare2_available() -> bool:
    """True when the radare2 integration can run.

    The radare2 server drives r2 through the ``r2pipe`` Python binding, which is a
    `binary-tools` (lab-host-only) dependency *separate* from the radare2 CLI: a
    host can have ``/usr/bin/r2`` installed as a system package while ``r2pipe`` is
    absent from the venv. The test needs both — r2pipe to import, and the r2 CLI
    for r2pipe to spawn — so check both, otherwise the test fails (not skips) on a
    host with the CLI but not the binding.
    """
    have_r2pipe = importlib.util.find_spec("r2pipe") is not None
    have_cli = shutil.which("r2") is not None or shutil.which("radare2") is not None
    return have_r2pipe and have_cli


def ropper_on_path() -> bool:
    """True when the ropper CLI is resolvable on $PATH."""
    return shutil.which("ropper") is not None


def gdb_on_path() -> bool:
    """True when the gdb CLI is resolvable on $PATH."""
    return shutil.which("gdb") is not None


def ghidra_available() -> bool:
    """True when the Ghidra tools can actually run.

    Both pieces are required: the **PyGhidra bridge must be importable** and a
    **Ghidra install must be discoverable** for it to start. PyGhidra's
    ``start()`` resolves the distribution via ``GHIDRA_INSTALL_DIR`` (or a
    ``ghidra`` on ``$PATH``). Requiring the import too means a host that has the
    install dir set but no ``pyghidra`` wheel *skips* the integration tests
    rather than running and failing them with ``ModuleNotFoundError``.
    """
    if importlib.util.find_spec("pyghidra") is None:
        return False
    if shutil.which("ghidra") is not None:
        return True
    install_dir = os.environ.get("GHIDRA_INSTALL_DIR")
    return install_dir is not None and Path(install_dir).is_dir()


# Marker name -> predicate that is True when the tool is present. A test bearing
# one of these markers is skipped (not failed) when its tool is absent, so the
# binary-tool integration tests skip on CI and run on the lab host.
_TOOL_MARKERS: dict[str, tuple[str, object]] = {
    "requires_ropgadget": ("ROPgadget", ropgadget_on_path),
    "requires_radare2": ("radare2 (r2pipe binding)", radare2_available),
    "requires_ropper": ("ropper", ropper_on_path),
    "requires_gdb": ("gdb", gdb_on_path),
    "requires_ghidra": ("Ghidra/PyGhidra", ghidra_available),
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip binary-tool integration tests (don't fail them) when the tool is absent.

    Each `requires_<tool>` marker skips when its tool is not resolvable, so the
    integration tests skip in CI (which lacks the `binary-tools` host) and run on
    the lab host where the tools are installed.
    """
    skips = {
        marker: pytest.mark.skip(reason=f"{label} not available")
        for marker, (label, predicate) in _TOOL_MARKERS.items()
        if not predicate()  # type: ignore[operator]
    }
    if not skips:
        return
    for item in items:
        for marker, skip in skips.items():
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to `tests/fixtures`."""
    return _FIXTURES


@pytest.fixture(scope="session")
def sample_overflow_path() -> Path:
    """Absolute path to the `sample_overflow` fixture binary."""
    return _FIXTURES / "binaries" / "sample_overflow"


@pytest.fixture
def fixture_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """A throwaway corpus rooted at ``tmp_path`` exposing the fixture binary.

    Builds ``corpus/{manifest.yaml,binaries/,exploits/}`` from the
    ``sample_overflow`` fixture (binary id ``sample-overflow``), points the
    ``SARA_CORPUS_*`` env vars at it, and returns a namespace with the documented
    addresses + success marker so harness tests can run the real resolver, runner,
    matrix, and CLI without touching the gitignored production corpus.
    """
    import json
    import shutil
    from types import SimpleNamespace

    import yaml

    src = _FIXTURES / "binaries"
    root = tmp_path / "corpus"
    bins = root / "binaries"
    exps = root / "exploits"
    bins.mkdir(parents=True)
    exps.mkdir(parents=True)

    shutil.copy(src / "sample_overflow", bins / "sample-overflow")
    # The documented-exploit module + its chain.json (build_payload reads its own
    # directory's chain.json), named by binary id for the verify path.
    shutil.copy(src / "exploit.py", exps / "sample-overflow.py")
    shutil.copy(src / "chain.json", exps / "chain.json")

    chain = json.loads((src / "chain.json").read_text(encoding="utf-8"))
    addresses = list(chain["documented_gadget_addresses"])
    marker = str(chain["success_marker"])

    manifest = {
        "binaries": [
            {
                "id": "sample-overflow",
                "name": "fixture sample_overflow",
                "architecture": "x86_64",
                "protections": ["nx"],
                "difficulty_tier": 1,
                "documented_vuln_class": "stack_overflow",
                "documented_gadget_addresses": addresses,
                "success_marker": marker,
            }
        ]
    }
    manifest_file = root / "manifest.yaml"
    manifest_file.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    monkeypatch.setenv("SARA_CORPUS_MANIFEST", str(manifest_file))
    monkeypatch.setenv("SARA_CORPUS_BINARIES_DIR", str(bins))
    monkeypatch.setenv("SARA_CORPUS_EXPLOITS_DIR", str(exps))

    return SimpleNamespace(
        root=root,
        binary_id="sample-overflow",
        binary_path=bins / "sample-overflow",
        addresses=[int(a, 16) for a in addresses],
        marker=marker,
    )


@pytest.fixture(scope="session")
def documented_exploit() -> object:
    """The fixture's `exploit` module (corpus-truth payload + chain metadata).

    Loaded by path so tests can call `build_payload()` / `load_chain()` without
    `tests/fixtures/binaries` being importable as a package.
    """
    import importlib.util

    path = _FIXTURES / "binaries" / "exploit.py"
    spec = importlib.util.spec_from_file_location("sara_fixture_exploit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
