# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""
Prompting strategies.

A 'prompting strategy' is a named bundle of:
  - system prompt
  - tool descriptions (may differ by strategy: ReAct includes scratchpad
    instructions, zero-shot does not, etc.)
  - any pre-processing of the user's task statement

Strategies are independent variables in the experiment. Adding a strategy
means adding a new module here and registering it in STRATEGIES.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent.prompts import chain_of_thought, majorca, react, zero_shot


@dataclass(frozen=True)
class Strategy:
    """Static bundle of prompt material for a named strategy."""

    name: str
    system_prompt: str
    tool_use_guidance: str
    task_template: Callable[[str], str]


STRATEGIES: dict[str, Strategy] = {
    "zero_shot": Strategy(
        name="zero_shot",
        system_prompt=zero_shot.SYSTEM,
        tool_use_guidance=zero_shot.TOOL_USE,
        task_template=zero_shot.task,
    ),
    "chain_of_thought": Strategy(
        name="chain_of_thought",
        system_prompt=chain_of_thought.SYSTEM,
        tool_use_guidance=chain_of_thought.TOOL_USE,
        task_template=chain_of_thought.task,
    ),
    "react": Strategy(
        name="react",
        system_prompt=react.SYSTEM,
        tool_use_guidance=react.TOOL_USE,
        task_template=react.task,
    ),
    "majorca": Strategy(
        name="majorca",
        system_prompt=majorca.SYSTEM,
        tool_use_guidance=majorca.TOOL_USE,
        task_template=majorca.task,
    ),
}


def get(name: str) -> Strategy:
    """Look up a strategy by name. Raises KeyError if unknown."""
    return STRATEGIES[name]


__all__ = ["STRATEGIES", "Strategy", "get"]
