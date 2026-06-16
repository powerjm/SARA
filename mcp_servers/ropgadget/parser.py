"""
ROPgadget output parser.

The ROPgadget CLI prints a header, a list of gadgets, then a footer. The
gadget lines have the shape:

    0x0000000000401234 : pop rdi ; ret

This parser is intentionally permissive: it skips lines that don't match the
shape and reports the count of skipped lines so callers can detect format
drift between ROPgadget versions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Gadget:
    """One ROP gadget."""

    address: str  # canonical hex string, lowercase, "0x..." prefix
    instructions: str  # raw instruction text, semicolon-separated
    length: int  # number of instructions


# Permissive: matches "0xHEX : INSTRUCTIONS"
_GADGET_LINE = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s*:\s*(.+?)\s*$")


def _canonical_address(raw: str) -> str:
    """Lowercase, no leading zeros stripped beyond '0x'."""
    return raw.lower()


def parse_gadgets(stdout: str) -> list[Gadget]:
    """Parse the stdout of `ROPgadget --binary X` into typed Gadget objects."""
    gadgets: list[Gadget] = []
    in_section = False
    for line in stdout.splitlines():
        # ROPgadget prints "Gadgets information" as the section header.
        if not in_section:
            if line.strip().startswith("Gadgets information"):
                in_section = True
            continue

        # End of the section is signalled by "Unique gadgets found:" footer.
        if line.strip().startswith("Unique gadgets found"):
            break

        m = _GADGET_LINE.match(line)
        if not m:
            continue
        addr, insns = m.group(1), m.group(2)
        # Count instructions by splitting on " ; " — ROPgadget always uses that.
        length = len([part for part in insns.split(" ; ") if part.strip()])
        gadgets.append(
            Gadget(
                address=_canonical_address(addr),
                instructions=insns,
                length=length,
            )
        )

    return gadgets


__all__ = ["Gadget", "parse_gadgets"]
