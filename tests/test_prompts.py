# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the prompting-strategy registry (`agent/prompts`).

Covers the invariants every strategy must satisfy, the consistency of the
registry with the `PromptingStrategy` schema enum and the CLI `--strategy`
choices (so adding a strategy in one place but not the others is caught), and
the MAJORCA strategy specifically.
"""

from __future__ import annotations

import pytest

from agent import prompts
from harness.cli import run as run_command
from harness.record import PromptingStrategy


def _strategy_choice_param() -> object:
    """The click ``--strategy`` option object on the ``run`` command."""
    (option,) = [p for p in run_command.params if p.name == "strategy"]
    return option


def test_registry_keys_match_schema_enum() -> None:
    """Every registered strategy is a schema value and vice versa.

    ``agent/graph.py`` builds ``PromptingStrategy(config.strategy.name)`` at
    record time, so a registry key with no enum member would crash a real run.
    """
    assert set(prompts.STRATEGIES) == {s.value for s in PromptingStrategy}


def test_cli_choices_match_registry() -> None:
    """The CLI ``--strategy`` choices stay in sync with the registry."""
    choices = set(_strategy_choice_param().type.choices)  # type: ignore[attr-defined]
    assert choices == set(prompts.STRATEGIES)


@pytest.mark.parametrize("name", sorted(prompts.STRATEGIES))
def test_strategy_is_well_formed(name: str) -> None:
    strategy = prompts.get(name)
    assert strategy.name == name
    # A run constructs PromptingStrategy(strategy.name); it must be a valid value.
    assert PromptingStrategy(strategy.name) == PromptingStrategy(name)
    assert strategy.system_prompt.strip()
    assert strategy.tool_use_guidance.strip()
    task = strategy.task_template("sample-overflow")
    assert isinstance(task, str)
    assert "sample-overflow" in task
    # Every strategy must point the agent at its terminal action.
    assert "submit_payload" in strategy.system_prompt + strategy.tool_use_guidance + task


def test_get_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError):
        prompts.get("wishful_thinking")


def test_majorca_registered_and_constructible() -> None:
    assert "majorca" in prompts.STRATEGIES
    assert PromptingStrategy("majorca") is PromptingStrategy.MAJORCA
    assert prompts.get("majorca").name == "majorca"


def test_majorca_prompt_encodes_the_methodology() -> None:
    """The MAJORCA prompt must carry the paper's four-stage scaffold and
    vocabulary — the whole point of the strategy is fidelity to the method."""
    system = prompts.get("majorca").system_prompt
    assert "MAJORCA" in system
    # The four stages, in the paper's language.
    for stage in ("Searching for gadgets", "gadget semantics", "Combining gadgets", "input data"):
        assert stage in system
    # Semantic taxonomy + chain-generation DAGs + scheduling + restricted symbols.
    for term in ("LoadConst", "StoreMem", "MoveChain", "LoadDAG", "StoreMemDAG", "(Sys)CallDAG"):
        assert term in system
    assert "execve" in system
