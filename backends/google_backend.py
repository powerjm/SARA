"""
Google Gemini backend (Premium category).

Same contract as the other backends (``anthropic_backend.py`` is the worked
example): map the provider-agnostic ``Message``/``ToolSpec`` onto Gemini's
``generate_content`` request, translate the response into a normalized
``ChatResponse`` with token usage and a USD cost from a pinned table, and detect
refusals. Gemini signals a policy block through the candidate's ``finish_reason``
(``SAFETY`` / ``PROHIBITED_CONTENT`` / ``BLOCKLIST`` / ``RECITATION``), so this
backend overrides ``_refusal_from_metadata`` to recognise those.

The model client is injectable (``client=``) so a cassette test can replay a
canned response without network or an API key.
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
PRICING: dict[str, Pricing] = pricing.subset(["gemini-2.5-pro", "gemini-2.5-flash"])

# Gemini finish reasons that mean the model declined / was content-filtered.
_REFUSAL_FINISH_REASONS = frozenset(
    {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION", "SPII"}
)


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


class GoogleBackend(Backend):
    """Google Gemini backend (Premium category)."""

    category = BackendCategory.PREMIUM

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        *,
        temperature: float = 0.2,
        seed: int | None = 0,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(temperature=temperature, seed=seed)
        self.name = model
        self.version = model

        if client is not None:
            self._model = client
            return
        key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GOOGLE_API_KEY not set. Put it in .env or export it.")
        import google.generativeai as genai

        genai.configure(api_key=key)  # type: ignore[attr-defined]
        self._model = genai.GenerativeModel(model)  # type: ignore[attr-defined]

    # --- Interface ------------------------------------------------------- #

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> ChatResponse:
        contents = _to_gemini_contents(messages)
        gen_tools = [_to_gemini_tool(t) for t in tools] or None
        resp = self._model.generate_content(
            contents,
            tools=gen_tools,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": max_tokens,
            },
        )

        candidate = resp.candidates[0]
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for part in candidate.content.parts:
            if getattr(part, "text", None):
                text_parts.append(part.text)
            call = getattr(part, "function_call", None)
            if call is not None and getattr(call, "name", None):
                tool_calls.append(
                    {"id": call.name, "name": call.name, "input": dict(call.args or {})}
                )

        usage = resp.usage_metadata
        tokens = TokenUsage(
            prompt=getattr(usage, "prompt_token_count", 0),
            completion=getattr(usage, "candidates_token_count", 0),
        )
        return ChatResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            tokens=tokens,
            cost=_compute_cost(self.name, tokens),
            raw={"finish_reason": str(candidate.finish_reason)},
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _refusal_from_metadata(self, response: ChatResponse) -> bool | None:
        """Recognise Gemini's safety/blocklist finish reasons as refusals."""
        raw = response.raw
        if isinstance(raw, dict):
            reason = str(raw.get("finish_reason", ""))
            if any(token in reason for token in _REFUSAL_FINISH_REASONS):
                return True
        return super()._refusal_from_metadata(response)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _to_gemini_contents(messages: list[Message]) -> list[dict[str, Any]]:
    """Map provider-agnostic messages onto Gemini ``contents``.

    Gemini has no separate system role and uses ``model`` for assistant turns;
    system text is folded into a leading user turn, and tool results are rendered
    as user text (the loop reasons over the text, not a structured result).
    """
    contents: list[dict[str, Any]] = []
    system_text: list[str] = []
    for message in messages:
        if message.role == "system":
            system_text.append(message.content)
            continue
        if message.role == "tool":
            contents.append(
                {"role": "user", "parts": [{"text": f"Tool result:\n{message.content}"}]}
            )
            continue
        role = "model" if message.role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message.content}]})

    if system_text:
        contents.insert(0, {"role": "user", "parts": [{"text": "\n\n".join(system_text)}]})
    return contents


def _to_gemini_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "function_declarations": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
        ]
    }


__all__ = ["PRICING", "GoogleBackend", "Pricing"]
