# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the Trial-3 automatable pre-flight checks (Phase D)."""

from __future__ import annotations

from harness.preflight import LAB_HOST_CHECKLIST, automatable_checks, main


def test_all_automatable_checks_pass_on_current_config() -> None:
    checks = automatable_checks()
    failed = [c.name for c in checks if not c.ok]
    assert failed == [], failed


def test_main_returns_zero_when_configured() -> None:
    assert main() == 0


def test_checks_cover_the_trial3_levers() -> None:
    names = " ".join(c.name for c in automatable_checks())
    assert "tool surface" in names  # ADR 0019
    assert "specialist arms" in names  # ADR 0021
    assert "schema default is v6" in names  # ADR 0020/0024
    assert "bonus scoring" in names  # ADR 0020
    assert "caching" in names  # ADR 0023
    assert "compaction" in names  # ADR 0022


def test_lab_host_checklist_names_the_manual_gates() -> None:
    joined = " ".join(LAB_HOST_CHECKLIST).lower()
    # The gates that genuinely need the lab host are enumerated for the operator.
    assert "procps" in joined
    assert "n_ctx_loaded >= 32768" in joined
    assert "tok/s" in joined
    assert "token-delta" in joined
    assert "cache-hit" in joined
