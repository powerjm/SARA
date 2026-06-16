"""Tests for corpus/scripts/build.py (the cb-multios build-and-pin helper).

Exercises the pure, side-effect-free helpers directly, plus the orchestration
path with the module's manifest/binaries dirs redirected to a tmp tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus.scripts import build

_ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_ZERO = "0" * 64


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --- cgc_id_for ----------------------------------------------------------- #


def test_cgc_id_derived_from_manifest_id() -> None:
    assert build.cgc_id_for({"id": "cgc-cromu-00004"}) == "CROMU_00004"
    assert build.cgc_id_for({"id": "cgc-cadet-00001"}) == "CADET_00001"


def test_cgc_id_explicit_build_override_wins() -> None:
    entry = {"id": "cgc-cromu-00004", "build": {"challenge": "Audio_Decoder"}}
    assert build.cgc_id_for(entry) == "Audio_Decoder"


# --- sha256_of ------------------------------------------------------------ #


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    import hashlib

    blob = b"the quick brown fox" * 1000
    f = _write(tmp_path / "blob", blob)
    assert build.sha256_of(f) == hashlib.sha256(blob).hexdigest()


# --- resolve_cb_dir ------------------------------------------------------- #


def test_resolve_cb_dir_finds_renamed_challenge(tmp_path: Path) -> None:
    cb = tmp_path / "cb-multios"
    _write(cb / "challenges" / "Audio_Decoder" / "README.md", b"port of CROMU_00004\n")
    _write(cb / "challenges" / "Other_Thing" / "README.md", b"port of NRFIN_00001\n")
    found = build.resolve_cb_dir(cb, "CROMU_00004")
    assert found is not None and found.name == "Audio_Decoder"


def test_resolve_cb_dir_none_when_absent(tmp_path: Path) -> None:
    cb = tmp_path / "cb-multios"
    _write(cb / "challenges" / "Other_Thing" / "README.md", b"port of NRFIN_00001\n")
    assert build.resolve_cb_dir(cb, "CROMU_00004") is None


def test_resolve_cb_dir_direct_name_match(tmp_path: Path) -> None:
    cb = tmp_path / "cb-multios"
    (cb / "challenges" / "CROMU_00004").mkdir(parents=True)
    found = build.resolve_cb_dir(cb, "CROMU_00004")
    assert found is not None and found.name == "CROMU_00004"


# --- locate_built_binary -------------------------------------------------- #


def test_locate_prefers_unpatched_elf_in_build_tree(tmp_path: Path) -> None:
    cb = tmp_path / "cb-multios"
    challenge = cb / "challenges" / "Audio_Decoder"
    challenge.mkdir(parents=True)
    built = _write(cb / "build" / "challenges" / "Audio_Decoder" / "Audio_Decoder", _ELF)
    _write(cb / "build" / "challenges" / "Audio_Decoder" / "Audio_Decoder_patched", _ELF)
    found = build.locate_built_binary(cb, challenge)
    assert found == built


def test_locate_skips_non_elf(tmp_path: Path) -> None:
    cb = tmp_path / "cb-multios"
    challenge = cb / "challenges" / "Audio_Decoder"
    challenge.mkdir(parents=True)
    # A same-named non-ELF (e.g. a source/object stub) must not be picked.
    _write(cb / "build" / "Audio_Decoder", b"not an elf")
    assert build.locate_built_binary(cb, challenge) is None


# --- repin_manifest_text -------------------------------------------------- #

_MANIFEST = (
    "binaries:\n"
    "  - id: alpha\n"
    f'    sha256: "{_ZERO}"\n'
    "    architecture: i386  # keep this comment\n"
    "  - id: beta\n"
    f'    sha256: "{_SHA_B}"\n'
)


def test_repin_updates_only_target_block() -> None:
    out = build.repin_manifest_text(_MANIFEST, "alpha", _SHA_A)
    assert f'sha256: "{_SHA_A}"' in out
    assert f'sha256: "{_SHA_B}"' in out  # beta untouched
    assert "# keep this comment" in out  # comments preserved
    assert out.count(_ZERO) == 0


def test_repin_last_entry_without_trailing_id() -> None:
    out = build.repin_manifest_text(_MANIFEST, "beta", _SHA_A)
    # beta repinned; alpha's placeholder zero pin is left alone.
    assert f'sha256: "{_SHA_A}"' in out
    assert _ZERO in out


def test_repin_unknown_entry_raises() -> None:
    with pytest.raises(KeyError):
        build.repin_manifest_text(_MANIFEST, "gamma", _SHA_A)


# --- build_one orchestration ---------------------------------------------- #


def test_build_one_from_path_pins_and_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write(
        tmp_path / "manifest.yaml",
        (
            "binaries:\n"
            "  - id: cgc-x\n"
            '    source_url: "git+https://example/repo"\n'
            f'    sha256: "{_ZERO}"\n'
        ).encode(),
    )
    bins = tmp_path / "binaries"
    monkeypatch.setattr(build, "MANIFEST", manifest)
    monkeypatch.setattr(build, "BINARIES_DIR", bins)

    elf = _write(tmp_path / "built_elf", _ELF)
    entry = {"id": "cgc-x", "source_url": "git+https://example/repo", "sha256": _ZERO}

    ok = build.build_one(entry, cb_root=None, from_path=elf, update=True)
    assert ok is True
    installed = bins / "cgc-x"
    assert installed.is_file() and installed.read_bytes() == _ELF
    assert f'sha256: "{build.sha256_of(elf)}"' in manifest.read_text(encoding="utf-8")


def test_build_one_from_path_rejects_non_elf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "MANIFEST", _write(tmp_path / "m.yaml", b"binaries: []\n"))
    monkeypatch.setattr(build, "BINARIES_DIR", tmp_path / "binaries")
    not_elf = _write(tmp_path / "junk", b"nope")
    entry = {"id": "cgc-x", "sha256": _ZERO}
    assert build.build_one(entry, cb_root=None, from_path=not_elf, update=True) is False


def test_build_one_mismatch_without_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "MANIFEST", _write(tmp_path / "m.yaml", b"binaries: []\n"))
    monkeypatch.setattr(build, "BINARIES_DIR", tmp_path / "binaries")
    elf = _write(tmp_path / "built_elf", _ELF)
    entry = {"id": "cgc-x", "sha256": _SHA_B}  # wrong pin, update not set
    assert build.build_one(entry, cb_root=None, from_path=elf, update=False) is False
    assert not (tmp_path / "binaries" / "cgc-x").exists()
