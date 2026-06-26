#!/usr/bin/env python3
"""
Deliberate, reviewed updater for backends/pricing.yaml — the single source of
truth for model prices (ADR 0007).

Pricing is intentionally NOT fetched at run time: a recorded run's cost must be
reproducible forever, so rates are pinned in a versioned file and refreshed by
running this script, reviewing the diff, and committing. There is no stable,
machine-readable pricing API across providers, so `--fetch` only points you at
the source URLs for manual verification rather than scraping.

Usage:
  python scripts/refresh_pricing.py            # print the pinned table
  python scripts/refresh_pricing.py --check    # exit non-zero if rates are stale
  python scripts/refresh_pricing.py --fetch    # print source URLs to verify against
  python scripts/refresh_pricing.py --bump     # stamp pricing_version to today

Run from anywhere; the repo root is added to sys.path below.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from backends import pricing  # noqa: E402  (import after sys.path bootstrap)

# Keep in sync with harness/cli.py::_PRICING_MAX_AGE_DAYS.
_MAX_AGE_DAYS = 30
_PRICING_FILE = _REPO_ROOT / "backends" / "pricing.yaml"


def _print_table() -> None:
    print(f"pricing_version: {pricing.PRICING_VERSION}")
    print(f"{'model':<20} {'prompt/Mtok':>12} {'compl/Mtok':>12}  {'as_of':<12} source")
    for model, p in sorted(pricing.PRICES.items()):
        print(
            f"{model:<20} {p.prompt_per_mtok:>12.4g} {p.completion_per_mtok:>12.4g}"
            f"  {p.as_of:<12} {p.source}"
        )


def _check() -> int:
    age = pricing.age_days(date.today())
    print(
        f"pricing_version {pricing.PRICING_VERSION}; oldest rate as of "
        f"{pricing.oldest_as_of()} ({age}d old)"
    )
    if age > _MAX_AGE_DAYS:
        print(
            f"STALE: oldest rate is {age}d old (> {_MAX_AGE_DAYS}d). Verify prices "
            f"against the source URLs, edit {_PRICING_FILE.name}, then --bump.",
            file=sys.stderr,
        )
        return 1
    print("OK: pricing is within the freshness window.")
    return 0


def _fetch() -> None:
    print(
        "Automated scraping is intentionally not implemented (no stable pricing "
        "API; brittle and a reproducibility hazard). Verify each rate manually "
        "against its source, then edit backends/pricing.yaml and --bump:\n"
    )
    for model, p in sorted(pricing.PRICES.items()):
        print(f"  {model:<20} {p.source}")


def _bump() -> None:
    today = date.today().isoformat()
    text = _PRICING_FILE.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"^pricing_version:.*$",
        f'pricing_version: "{today}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        print("ERROR: could not find a 'pricing_version:' line to bump", file=sys.stderr)
        raise SystemExit(2)
    _PRICING_FILE.write_text(new_text, encoding="utf-8")
    print(f"bumped pricing_version -> {today} (review per-model as_of dates by hand)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="exit non-zero if rates are stale")
    group.add_argument("--fetch", action="store_true", help="print source URLs to verify against")
    group.add_argument("--bump", action="store_true", help="stamp pricing_version to today")
    args = parser.parse_args(argv)

    if args.check:
        return _check()
    if args.fetch:
        _fetch()
        return 0
    if args.bump:
        _bump()
        return 0
    _print_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
