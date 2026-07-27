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
Anthropic backend implementation.

This is the worked example of how to implement Backend. Other Premium backends
(OpenAI, Google) follow the same pattern; Open Weight backends use the
LM Studio adapter (which speaks OpenAI-compatible).

Pricing table is pinned to a specific model snapshot and should be updated
when the deployed model changes. The harness writes the recorded cost to the
RunRecord; analysis scripts re-compute from raw tokens if needed.
"""

from __future__ import annotations

import os
from typing import Any

from backends import pricing
from backends.base import Backend, ChatResponse, Message, ToolSpec
from backends.pricing import Pricing  # re-export: back-compat alias for ModelPrice
from harness.record import BackendCategory, CostRecord, TokenUsage

# --------------------------------------------------------------------------- #
# Pricing                                                                     #
# --------------------------------------------------------------------------- #

# Prices live in backends/pricing.yaml (single source of truth, refreshed via
# scripts/refresh_pricing.py). ``PRICING`` is a back-compat view over that file
# scoped to this provider's models; do not hard-code rates here.
PRICING: dict[str, Pricing] = pricing.subset(["claude-sonnet-4-6", "claude-opus-4-7"])


def _compute_cost(model: str, tokens: TokenUsage) -> CostRecord:
    p = pricing.price_for(model)
    if p is None:
        return CostRecord(usd=0.0)
    usd = (
        tokens.prompt * p.prompt_per_mtok + tokens.completion * p.completion_per_mtok
    ) / 1_000_000
    return CostRecord(usd=usd, pricing=pricing.snapshot_for(model))


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class AnthropicBackend(Backend):
    """Anthropic Messages API backend (Premium category)."""

    category = BackendCategory.PREMIUM

    # Prompt caching (ADR 0023): mark the stable prefix — the system prompt and the
    # tool schema — with ``cache_control: ephemeral`` so a cache hit re-bills that
    # (large, byte-stable) prefix at ~10%. SARA sends the whole tool schema and
    # system prompt every reason turn, and Trial-3 compaction keeps them byte-stable
    # while confining churn to the suffix, so the prefix is a cache hit on turn ≥2.
    # Cache-read/write counts come back in ``resp.usage`` and are surfaced via
    # ``ChatResponse.raw`` for the preflight cache-hit-rate gate.
    _prompt_cache: bool = True
    _CACHE_CONTROL: dict[str, str] = {"type": "ephemeral"}

    # Some Anthropic models (the opus reasoning line) deprecated the
    # ``temperature`` sampling param and return 400 ("temperature is deprecated
    # for this model") if it is sent, so the backend omits it for those models —
    # their runs are non-deterministic, an API limitation, mirroring the gpt-5
    # handling in OpenAIBackend. Sonnet still accepts and honors it.
    _MODELS_WITHOUT_TEMPERATURE: frozenset[str] = frozenset({"claude-opus-4-7"})

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        temperature: float = 0.2,
        seed: int | None = 0,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(temperature=temperature, seed=seed)
        self.name = model
        self.version = model
        # An injected client (tests) skips the key requirement and SDK import.
        if client is not None:
            self._client = client
            return
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Put it in .env or export it.")
        # Deferred import so test runs without the SDK don't break collection.
        from anthropic import Anthropic  # type: ignore[import-not-found]

        self._client = Anthropic(api_key=self._api_key)

    # --- Interface ------------------------------------------------------- #

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> ChatResponse:
        api_messages, system = _to_anthropic_messages(messages)
        api_tools = [_to_anthropic_tool(t) for t in tools]
        if self._prompt_cache:
            # Cache the stable prefix: the whole tool schema (mark the LAST tool —
            # the breakpoint caches every tool before it) and the system prompt.
            if api_tools:
                api_tools[-1] = {**api_tools[-1], "cache_control": self._CACHE_CONTROL}
            if system is not None:
                system = [  # type: ignore[assignment]
                    {"type": "text", "text": system, "cache_control": self._CACHE_CONTROL}
                ]

        kwargs: dict[str, Any] = {
            "model": self.name,
            "messages": api_messages,
            "tools": api_tools or None,
            "max_tokens": max_tokens,
        }
        if self.name not in self._MODELS_WITHOUT_TEMPERATURE:
            kwargs["temperature"] = self.temperature
        if system is not None:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)  # type: ignore[no-untyped-call]

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        tokens = TokenUsage(
            prompt=resp.usage.input_tokens,
            completion=resp.usage.output_tokens,
        )
        return ChatResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            tokens=tokens,
            cost=_compute_cost(self.name, tokens),
            raw=resp.model_dump(),
        )

    def count_tokens(self, text: str) -> int:
        # Rough estimate: ~4 chars/token. Used only for pre-flight budget checks;
        # actual usage is recorded from API response.
        return max(1, len(text) // 4)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _to_anthropic_messages(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], str | None]:
    """Translate the provider-agnostic log to Anthropic's Messages format.

    Anthropic differs from the OpenAI wire format the internal ``Message`` mirrors
    in three ways this handles:

    * **System** is a top-level field, not a message.
    * **Tool calls / results are content blocks**, not roles: an assistant tool
      call is a ``tool_use`` block; a ``tool`` message becomes a ``user`` turn
      carrying a ``tool_result`` block keyed by ``tool_use_id``.
    * **Roles must alternate** (no two consecutive user or assistant turns), so
      adjacent same-role turns — e.g. the user task followed by the user-context
      baseline enumeration (ADR 0011) — are merged into one turn with multiple
      content blocks.
    """
    system: str | None = None
    turns: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            system = m.content if system is None else system + "\n\n" + m.content
            continue

        role: str
        blocks: list[dict[str, Any]]
        if m.role == "tool":
            role = "user"
            blocks = [
                {"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content}
            ]
        elif m.role == "assistant":
            role = "assistant"
            blocks = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for call in m.tool_calls or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(call.get("name") or ""),
                        "input": call.get("input") or call.get("arguments") or {},
                    }
                )
        else:  # user
            role = "user"
            blocks = [{"type": "text", "text": m.content}] if m.content else []

        if not blocks:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": blocks})
    return turns, system


def _to_anthropic_tool(t: ToolSpec) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema,
    }


__all__ = ["AnthropicBackend", "PRICING", "Pricing"]
