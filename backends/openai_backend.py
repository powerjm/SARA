"""
OpenAI backend (Premium category).

Follows the worked example in ``anthropic_backend.py``: map the provider-agnostic
``Message``/``ToolSpec`` onto the OpenAI Chat Completions wire format, translate
the response back into a normalized ``ChatResponse`` with accurate token usage
and a USD cost from a pinned pricing table, and surface a refusal signal through
``ChatResponse.raw`` (``finish_reason``), which the base ``detect_refusal``
already understands (``content_filter``).

The SDK client is injectable (``client=``) so a cassette-style test can replay a
canned response object without network or an API key. Because LM Studio speaks
the same wire format, ``LMStudioBackend`` subclasses this backend and only swaps
the base URL, category, and pricing.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Import specific symbols (not the module) because ``pricing`` is a parameter
# name below; aliasing the module would shadow it.
from backends.base import Backend, ChatResponse, Message, ToolSpec
from backends.pricing import PRICING_VERSION, Pricing, subset
from harness.record import BackendCategory, CostRecord, PricingSnapshot, TokenUsage

# --------------------------------------------------------------------------- #
# Pricing                                                                     #
# --------------------------------------------------------------------------- #

# Prices live in backends/pricing.yaml (single source of truth, refreshed via
# scripts/refresh_pricing.py). ``PRICING`` is a back-compat view over that file
# scoped to this provider's models; do not hard-code rates here.
PRICING: dict[str, Pricing] = subset(["gpt-5", "gpt-5-mini"])


def _compute_cost(price: Pricing | None, tokens: TokenUsage) -> CostRecord:
    if price is None:
        return CostRecord(usd=0.0)
    usd = (
        tokens.prompt * price.prompt_per_mtok + tokens.completion * price.completion_per_mtok
    ) / 1_000_000
    snapshot = PricingSnapshot(
        prompt_per_mtok=price.prompt_per_mtok,
        completion_per_mtok=price.completion_per_mtok,
        pricing_version=PRICING_VERSION,
        as_of=price.as_of,
    )
    return CostRecord(usd=usd, pricing=snapshot)


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class OpenAIBackend(Backend):
    """OpenAI Chat Completions backend (Premium category)."""

    category = BackendCategory.PREMIUM

    def __init__(
        self,
        model: str = "gpt-5",
        *,
        temperature: float = 0.2,
        seed: int | None = 0,
        api_key: str | None = None,
        base_url: str | None = None,
        category: BackendCategory | None = None,
        pricing: Pricing | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(temperature=temperature, seed=seed)
        self.name = model
        self.version = model
        if category is not None:
            self.category = category
        # Pricing: explicit > pinned table > none (local/unpriced).
        self._pricing = pricing if pricing is not None else PRICING.get(model)

        if client is not None:
            self._client = client
            return
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set. Put it in .env or export it.")
        from openai import OpenAI

        self._client = OpenAI(api_key=key, base_url=base_url)

    # --- Interface ------------------------------------------------------- #

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> ChatResponse:
        api_tools = [_to_openai_tool(t) for t in tools]
        resp = self._client.chat.completions.create(
            model=self.name,
            messages=[_to_openai_message(m) for m in messages],
            tools=api_tools or None,
            max_tokens=max_tokens,
            temperature=self.temperature,
            seed=self.seed,
        )
        choice = resp.choices[0]
        message = choice.message
        text = message.content or ""

        tool_calls: list[dict[str, Any]] = []
        for call in getattr(message, "tool_calls", None) or []:
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": _parse_arguments(call.function.arguments),
                }
            )

        usage = resp.usage
        tokens = TokenUsage(
            prompt=getattr(usage, "prompt_tokens", 0),
            completion=getattr(usage, "completion_tokens", 0),
        )
        return ChatResponse(
            text=text,
            tool_calls=tool_calls,
            tokens=tokens,
            cost=_compute_cost(self._pricing, tokens),
            raw={"finish_reason": choice.finish_reason},
        )

    def count_tokens(self, text: str) -> int:
        # Heuristic ~4 chars/token, used only for pre-flight budget checks; the
        # recorded usage comes from the API response.
        return max(1, len(text) // 4)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _to_openai_message(message: Message) -> dict[str, Any]:
    """Map a provider-agnostic Message onto an OpenAI chat message dict."""
    if message.role == "tool":
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id or "",
        }
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": json.dumps(tc.get("input") or tc.get("arguments") or {}),
                },
            }
            for tc in message.tool_calls
        ]
    return out


def _to_openai_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    """Decode an OpenAI tool-call arguments JSON string into a dict."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["PRICING", "OpenAIBackend", "Pricing"]
