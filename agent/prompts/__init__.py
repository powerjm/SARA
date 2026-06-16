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

from agent.prompts import chain_of_thought, react, zero_shot


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
}


def get(name: str) -> Strategy:
    """Look up a strategy by name. Raises KeyError if unknown."""
    return STRATEGIES[name]


__all__ = ["STRATEGIES", "Strategy", "get"]
