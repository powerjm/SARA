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
LM Studio backend (Open Weight / Unrestricted categories).

LM Studio exposes an OpenAI-compatible endpoint at a configurable URL, so this
backend is just :class:`~backends.openai_backend.OpenAIBackend` pointed at that
endpoint: same Chat Completions wire format, same response translation. The one
endpoint serves **both** open-weight and unrestricted models — the category is
supplied at construction time so the ``RunRecord`` reflects the experimenter's a
priori classification (ADR 0005, decided on safety-alignment status).

Local models have no per-token price: cost is recorded as ``usd=0.0`` and the
harness attributes hardware cost from wall-clock instead (``CostRecord``), so the
backend passes ``pricing=None``.
"""

from __future__ import annotations

import os
from typing import Any

from backends.openai_backend import OpenAIBackend
from harness.record import BackendCategory


class LMStudioBackend(OpenAIBackend):
    """OpenAI-compatible backend talking to a local LM Studio endpoint."""

    # LM Studio's server accepts the legacy ``max_tokens`` field, not the
    # ``max_completion_tokens`` the real OpenAI API now requires (see the base
    # class); override back to keep local calls working. Local models honor the
    # determinism knobs, so re-enable temperature/seed the base backend omits.
    _max_output_param: str = "max_tokens"
    _send_sampling_params: bool = True

    def __init__(
        self,
        model: str,
        category: BackendCategory,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.2,
        seed: int | None = 0,
        client: Any = None,
    ) -> None:
        resolved_url = base_url or os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
        # LM Studio ignores the key but the OpenAI SDK requires a non-empty one.
        resolved_key = api_key or os.environ.get("LMSTUDIO_API_KEY", "lm-studio")
        super().__init__(
            model,
            temperature=temperature,
            seed=seed,
            api_key=resolved_key,
            base_url=resolved_url,
            category=category,
            pricing=None,  # local models record usd=0.0
            client=client,
        )
        self.base_url = resolved_url


__all__ = ["LMStudioBackend"]
