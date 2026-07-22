# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""ROPgadget MCP server."""

from mcp_servers.ropgadget.parser import Gadget, parse_gadgets
from mcp_servers.ropgadget.server import EnumerateResult, enumerate_gadgets

__all__ = ["EnumerateResult", "Gadget", "enumerate_gadgets", "parse_gadgets"]
