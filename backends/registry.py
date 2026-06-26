"""
Backend registry.

The single source of truth for "which backends does this experiment know
about." The CLI's --backend flag is resolved through here; new backends are
added by importing them and calling `register`.

Registration is deliberately explicit (no import-time side-effects beyond
this module's own `_register_defaults`) so the resolution order is auditable
in code review.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from backends import pricing as pricing_table
from backends.base import Backend
from harness.record import BackendCategory

# USD per million tokens, as (prompt, completion). ``None`` for backends with no
# per-token price (local / open-weight models served through LM Studio, the
# scripted fake). Exposed via ``pricing()`` so a dry-run cost estimate can be
# computed without instantiating a backend (which would need an API key).
Pricing = tuple[float, float]


@dataclass(frozen=True)
class _Entry:
    category: BackendCategory
    factory: Callable[[], Backend]
    # The API model string this cell resolves to (e.g. "claude-sonnet-4-6").
    # Pricing is derived from it through backends.pricing — the single source of
    # truth — so rates are never duplicated here. ``None`` for unpriced backends
    # (local LM Studio models, the scripted fake).
    model: str | None = None


# Name -> registry entry.
_REGISTRY: dict[str, _Entry] = {}


def register(
    name: str,
    category: BackendCategory,
    factory: Callable[[], Backend],
    *,
    model: str | None = None,
) -> None:
    """Add a backend to the registry. Raises if name is already taken."""
    if name in _REGISTRY:
        raise ValueError(f"backend {name!r} already registered")
    _REGISTRY[name] = _Entry(category=category, factory=factory, model=model)


def get(name: str) -> Backend:
    """Instantiate the named backend. Raises KeyError if unknown."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown backend: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name].factory()


def category(name: str) -> BackendCategory:
    """The declared category of a registered backend (no instantiation)."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown backend: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name].category


def pricing(name: str) -> Pricing | None:
    """The (prompt, completion) USD-per-Mtok pricing, or ``None`` if untracked.

    Derived from the cell's model via ``backends.pricing`` (the single source of
    truth) — rates are not stored on the registry entry, so they cannot drift
    from what the backends actually charge.
    """
    if name not in _REGISTRY:
        raise KeyError(f"unknown backend: {name!r}. Known: {sorted(_REGISTRY)}")
    model = _REGISTRY[name].model
    if model is None:
        return None
    return pricing_table.tuple_for(model)


def known() -> list[str]:
    """Sorted list of registered backend names."""
    return sorted(_REGISTRY)


def _register_defaults() -> None:
    """Wire up the default backends. Called at import time."""
    # Import inside the function so missing optional SDKs don't break
    # `import backends`. Pricing is derived from each cell's ``model`` through
    # backends.pricing (no rates duplicated here).
    from backends.anthropic_backend import AnthropicBackend

    register(
        "claude-sonnet",
        BackendCategory.PREMIUM,
        lambda: AnthropicBackend(model="claude-sonnet-4-6"),
        model="claude-sonnet-4-6",
    )
    register(
        "claude-opus",
        BackendCategory.PREMIUM,
        lambda: AnthropicBackend(model="claude-opus-4-7"),
        model="claude-opus-4-7",
    )

    # The scripted FakeBackend is a *test-only* backend: it is registered as
    # "fake" only when running under pytest (PYTEST_RUNNING=1, set by the test
    # conftest), never for a real run. This keeps `--backend fake` available to
    # CLI/integration tests while ensuring a run-for-record cannot accidentally
    # resolve it. `tests/` is on sys.path under pytest (conftest guarantees it).
    if os.environ.get("PYTEST_RUNNING") == "1":

        def _make_fake() -> Backend:
            # Imported lazily inside the factory so importing `backends` never
            # imports `fakes.backend` at module load — otherwise importing
            # `fakes.backend` first would recurse through this registration
            # before FakeBackend is defined (a circular import).
            from fakes.backend import FakeBackend

            backend: Backend = FakeBackend.from_env()
            return backend

        register("fake", BackendCategory.PREMIUM, _make_fake)

    # --- OpenAI (Premium) ---
    from backends.openai_backend import OpenAIBackend

    register(
        "gpt-5",
        BackendCategory.PREMIUM,
        lambda: OpenAIBackend(model="gpt-5"),
        model="gpt-5",
    )

    # --- Google Gemini (Premium) ---
    from backends.google_backend import GoogleBackend

    register(
        "gemini-2.5-pro",
        BackendCategory.PREMIUM,
        lambda: GoogleBackend(model="gemini-2.5-pro"),
        model="gemini-2.5-pro",
    )

    # --- LM Studio (local; Open Weight + Unrestricted, per ADR 0005) ---
    # The same endpoint serves both categories; the category is declared a priori
    # per model here (the single source of truth). Local models have no per-token
    # price, so no pricing is registered (cost is recorded as usd=0.0).
    from backends.lmstudio_backend import LMStudioBackend

    register(
        "llama-3.3-70b",
        BackendCategory.OPEN_WEIGHT,
        lambda: LMStudioBackend("llama-3.3-70b-instruct", BackendCategory.OPEN_WEIGHT),
    )
    register(
        "qwen2.5-coder-32b",
        BackendCategory.OPEN_WEIGHT,
        lambda: LMStudioBackend("qwen2.5-coder-32b-instruct", BackendCategory.OPEN_WEIGHT),
    )
    # Small, fast, strong-tool-calling sibling of the 32B above. Intended for
    # smoke-testing the LM Studio transport and the agent tool loop on modest
    # hardware (~6-8 GB VRAM at Q4) -- NOT a run-for-record model. Same
    # OPEN_WEIGHT category so an accidental real run is still correctly labelled.
    register(
        "qwen2.5-coder-7b",
        BackendCategory.OPEN_WEIGHT,
        lambda: LMStudioBackend("qwen2.5-coder-7b-instruct", BackendCategory.OPEN_WEIGHT),
    )
    register(
        "dolphin-mixtral-8x7b",
        BackendCategory.UNRESTRICTED,
        lambda: LMStudioBackend("dolphin-2.7-mixtral-8x7b", BackendCategory.UNRESTRICTED),
    )


# Calling at import time is intentional: the registry is global state for the
# whole process and the CLI relies on it being populated before any command
# runs. Backends fail their constructors if credentials are missing, but the
# constructors are lazy (wrapped in lambdas), so importing this module does
# not require API keys.
_register_defaults()


__all__ = ["Pricing", "category", "get", "known", "pricing", "register"]
