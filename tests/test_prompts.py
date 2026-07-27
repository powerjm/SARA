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
    # Every strategy must offer the agent both submission paths: the primary
    # iterate-on-script tool (ADR 0016) and the raw-bytes alternative.
    composed = strategy.system_prompt + strategy.tool_use_guidance + task
    assert "run_exploit_script" in composed
    assert "submit_payload" in composed


@pytest.mark.parametrize("name", sorted(prompts.STRATEGIES))
def test_every_strategy_states_the_success_criterion(name: str) -> None:
    """Every strategy must tell the model exactly what success requires — the
    marker string and the spawn-a-shell goal the validator scores (ADR 0009) —
    so the strategies differ in reasoning approach, not in goal knowledge. A
    strategy that omits this makes the task unwinnable (the marker is in neither
    the prompt nor the binaries) and confounds the cross-strategy comparison.
    """
    system = prompts.get(name).system_prompt
    from validator.runner import SUCCESS_MARKER

    assert SUCCESS_MARKER in system  # the exact marker, e.g. "HELLO SANS"
    assert "/bin/sh" in system  # the spawn-a-shell objective
    # The anti-echo constraint must be disclosed too, or knowing the marker is a
    # trap (echoing it fails).
    assert "anti-echo" in system.lower() or "not copied from your input" in system.lower()


@pytest.mark.parametrize("name", sorted(prompts.STRATEGIES))
def test_every_strategy_invites_iterative_testing(name: str) -> None:
    """Every strategy must tell the model it can execute candidates repeatedly
    (ADR 0014/0016); otherwise it tends to enumerate forever and never test an
    exploit, leaving the iterative-validation loop unused. Trial 2 makes the
    write-and-run-a-script workflow the primary path, stated neutrally."""
    # Collapse whitespace so the phrase checks are robust to line wrapping.
    system = " ".join(prompts.get(name).system_prompt.lower().split())
    assert "run_exploit_script" in system  # the primary iterate-on-script tool
    assert "as often as you like" in system  # the affordance: not one-shot
    assert "submit_payload" in system  # raw-bytes alternative retained


def test_get_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError):
        prompts.get("wishful_thinking")


def test_majorca_registered_and_constructible() -> None:
    assert "majorca" in prompts.STRATEGIES
    assert PromptingStrategy("majorca") is PromptingStrategy.MAJORCA
    assert prompts.get("majorca").name == "majorca"


# --- Trial-3 ROP-specialist arms (ADR 0021) -------------------------------- #

_TRIAL3_ARMS = ("template_backward", "recon_first")


@pytest.mark.parametrize("name", _TRIAL3_ARMS)
def test_trial3_arm_registered_and_constructible(name: str) -> None:
    assert name in prompts.STRATEGIES
    assert PromptingStrategy(name).value == name
    assert prompts.get(name).name == name


@pytest.mark.parametrize("name", _TRIAL3_ARMS)
def test_trial3_arm_carries_methodology_rubric_and_idiom(name: str) -> None:
    system = prompts.get(name).system_prompt
    # Expert methodology (Mechanism 1): names techniques without a target's answer.
    assert "work backward from execve" in system
    assert "move-chain" in system
    assert "arithmetic byte-synthesis" in system
    # 100-pt rubric disclosed at face value, including the (unwinnable) root bonus.
    assert "SCORING (100 points)" in system
    assert "root (uid=0)" in system
    # Trailing-stdin marker idiom.
    assert "target < payload" in system
    assert 'echo "$A $B"' in system
    # It advertises the curated find_gadget tool, not the retired dumps.
    composed = system + prompts.get(name).tool_use_guidance
    assert "find_gadget" in composed


def test_trial3_shared_fragment_is_identical_across_arms() -> None:
    # The two arms must differ ONLY in their reasoning scaffold, so the shared
    # expert fragment (methodology + rubric + idiom + criterion + iterate loop)
    # is byte-identical in both — the fixed-condition guarantee (ADR 0021).
    from agent.prompts import (
        EXPERT_METHODOLOGY,
        MARKER_IDIOM,
        SCORING_RUBRIC,
    )

    for fragment in (EXPERT_METHODOLOGY, SCORING_RUBRIC, MARKER_IDIOM):
        for name in _TRIAL3_ARMS:
            assert fragment in prompts.get(name).system_prompt
    # And the scaffolds genuinely differ (not two copies of one arm).
    assert (
        prompts.get("template_backward").system_prompt != prompts.get("recon_first").system_prompt
    )


def test_generic_arms_do_not_carry_the_trial3_rubric() -> None:
    # The 100-pt rubric is a Trial-3 specialist-arm addition; the retired generic
    # arms keep their original framing (they are out of the Trial-3 matrix).
    for name in ("zero_shot", "chain_of_thought", "react", "majorca"):
        assert "SCORING (100 points)" not in prompts.get(name).system_prompt


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
