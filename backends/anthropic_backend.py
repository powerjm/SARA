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

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        temperature: float = 0.2,
        seed: int | None = 0,
        api_key: str | None = None,
    ) -> None:
        super().__init__(temperature=temperature, seed=seed)
        self.name = model
        self.version = model
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

        resp = self._client.messages.create(  # type: ignore[no-untyped-call]
            model=self.name,
            system=system,
            messages=api_messages,
            tools=api_tools or None,
            max_tokens=max_tokens,
            temperature=self.temperature,
        )

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
    """Split out system message (Anthropic API takes it as a top-level field)."""
    system: str | None = None
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            system = m.content if system is None else system + "\n\n" + m.content
            continue
        out.append({"role": m.role, "content": m.content})
    return out, system


def _to_anthropic_tool(t: ToolSpec) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema,
    }


__all__ = ["AnthropicBackend", "PRICING", "Pricing"]
