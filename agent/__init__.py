# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Agent state machine, prompts, and routing logic."""

from agent.graph import (
    AgentConfig,
    AgentResult,
    build_graph,
    build_run_record,
    classify_outcome,
    run_agent,
)
from agent.state import AgentState, BinaryContext, Message, ToolObservation
from agent.tools import ToolLayer

__all__ = [
    "AgentConfig",
    "AgentResult",
    "AgentState",
    "BinaryContext",
    "Message",
    "ToolLayer",
    "ToolObservation",
    "build_graph",
    "build_run_record",
    "classify_outcome",
    "run_agent",
]
