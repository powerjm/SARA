# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Cassette-style tests for the Step-7 backends.

Each backend is driven by an injected fake SDK client that replays a canned
response, so these run on CI with no network and no API key. They assert the
normalized ``ChatResponse`` (text, tool calls, token usage, USD cost) and the
provider-specific refusal signal.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backends import pricing
from backends.anthropic_backend import _to_anthropic_messages
from backends.base import Message, ToolSpec
from backends.google_backend import GoogleBackend, _sanitize_schema, _to_gemini_contents
from backends.lmstudio_backend import LMStudioBackend
from backends.openai_backend import OpenAIBackend
from harness.record import BackendCategory

_TOOLS = [ToolSpec(name="enumerate_gadgets", description="d", input_schema={"type": "object"})]
_MESSAGES = [Message(role="system", content="sys"), Message(role="user", content="hi")]


# --------------------------------------------------------------------------- #
# OpenAI                                                                      #
# --------------------------------------------------------------------------- #


def _openai_client(
    *,
    content: str | None,
    tool_calls: list[Any] | None = None,
    finish: str = "stop",
    prompt: int = 100,
    completion: int = 20,
) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish)
    resp = SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )
    create = SimpleNamespace(create=lambda **kw: resp)
    return SimpleNamespace(chat=SimpleNamespace(completions=create))


def test_openai_text_response_and_cost() -> None:
    backend = OpenAIBackend(model="gpt-5", client=_openai_client(content="hello"))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.text == "hello"
    assert resp.tool_calls == []
    assert resp.tokens.prompt == 100
    assert resp.tokens.completion == 20
    # gpt-5 priced (1.25, 10.0)/Mtok -> 100*1.25e-6 + 20*10e-6.
    assert resp.cost.usd == (100 * 1.25 + 20 * 10.0) / 1_000_000
    # The rates that produced the cost are recorded for later audit.
    assert resp.cost.pricing is not None
    assert resp.cost.pricing.prompt_per_mtok == 1.25
    assert resp.cost.pricing.completion_per_mtok == 10.0
    assert resp.cost.pricing.pricing_version == pricing.PRICING_VERSION


def test_openai_parses_tool_calls() -> None:
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="enumerate_gadgets", arguments='{"binary_path": "x"}'),
    )
    backend = OpenAIBackend(model="gpt-5", client=_openai_client(content=None, tool_calls=[tc]))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.tool_calls == [
        {"id": "call_1", "name": "enumerate_gadgets", "arguments": {"binary_path": "x"}}
    ]


def test_openai_refusal_via_finish_reason() -> None:
    backend = OpenAIBackend(
        model="gpt-5", client=_openai_client(content="", finish="content_filter")
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert backend.detect_refusal(resp)


# --------------------------------------------------------------------------- #
# LM Studio (OpenAI-compatible; local -> no token cost)                        #
# --------------------------------------------------------------------------- #


def test_lmstudio_zero_cost_and_category() -> None:
    backend = LMStudioBackend(
        "qwen/qwen2.5-coder-32b",
        BackendCategory.OPEN_WEIGHT,
        client=_openai_client(content="local reply"),
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.text == "local reply"
    assert resp.cost.usd == 0.0  # local models record no token cost
    assert resp.cost.pricing is None  # ... and carry no pricing snapshot
    assert backend.category == BackendCategory.OPEN_WEIGHT


def test_lmstudio_unrestricted_category() -> None:
    backend = LMStudioBackend(
        "cognitivecomputations_dolphin3.0-mistral-24b",
        BackendCategory.UNRESTRICTED,
        client=_openai_client(content="x"),
    )
    assert backend.category == BackendCategory.UNRESTRICTED


# --- schema v6: n_ctx_loaded telemetry (ADR 0024) -------------------------- #


def test_lmstudio_loaded_ctx_parsing_matches_model() -> None:
    from backends.lmstudio_backend import _loaded_ctx_from_models

    payload = {
        "data": [
            {"id": "gpt-oss-20b", "state": "loaded", "loaded_context_length": 32768},
            {"id": "other-model", "state": "not-loaded", "max_context_length": 4096},
        ]
    }
    assert _loaded_ctx_from_models(payload, "gpt-oss-20b") == 32768


def test_lmstudio_loaded_ctx_falls_back_to_single_loaded_entry() -> None:
    from backends.lmstudio_backend import _loaded_ctx_from_models

    # Model id mismatch (LM Studio sometimes advertises a different id string), but
    # exactly one model is loaded -> report its context.
    payload = {"data": [{"id": "served-alias", "state": "loaded", "loaded_context_length": 65536}]}
    assert _loaded_ctx_from_models(payload, "the-model-i-asked-for") == 65536


def test_lmstudio_loaded_ctx_none_when_absent_or_malformed() -> None:
    from backends.lmstudio_backend import _loaded_ctx_from_models

    assert _loaded_ctx_from_models({}, "m") is None
    assert _loaded_ctx_from_models({"data": "nope"}, "m") is None
    assert _loaded_ctx_from_models({"data": []}, "m") is None
    # A loaded entry with no context length is unusable -> None, not a guess.
    assert _loaded_ctx_from_models({"data": [{"id": "m", "state": "loaded"}]}, "m") is None


def test_lmstudio_n_ctx_loaded_is_defensive_on_network_failure() -> None:
    # No server reachable at the (unused) default URL: the probe must return None,
    # never raise, so a telemetry gap can't abort a run.
    backend = LMStudioBackend(
        "gpt-oss-20b",
        BackendCategory.OPEN_WEIGHT,
        base_url="http://127.0.0.1:9/v1",  # port 9 (discard) — connection refused
        client=_openai_client(content="x"),
    )
    assert backend.n_ctx_loaded() is None


def test_premium_backend_reports_no_loaded_ctx() -> None:
    # Hosted/premium backends serve a fixed provider context -> None.
    from backends.openai_backend import OpenAIBackend

    backend = OpenAIBackend("gpt-5", client=_openai_client(content="x"))
    assert backend.n_ctx_loaded() is None


# --------------------------------------------------------------------------- #
# Google Gemini                                                               #
# --------------------------------------------------------------------------- #


def _gemini_client(
    *, parts: list[Any], finish: str = "STOP", prompt: int = 100, completion: int = 20
) -> Any:
    cand = SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason=finish)
    resp = SimpleNamespace(
        candidates=[cand],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt, candidates_token_count=completion
        ),
    )
    return SimpleNamespace(generate_content=lambda *a, **kw: resp)


def test_google_text_response_and_cost() -> None:
    part = SimpleNamespace(text="gemini hello")
    backend = GoogleBackend(model="gemini-pro-latest", client=_gemini_client(parts=[part]))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.text == "gemini hello"
    assert resp.tokens.prompt == 100
    assert resp.cost.usd == (100 * 2.0 + 20 * 12.0) / 1_000_000
    assert resp.cost.pricing is not None
    assert resp.cost.pricing.pricing_version == pricing.PRICING_VERSION


def test_google_parses_function_call() -> None:
    part = SimpleNamespace(
        function_call=SimpleNamespace(name="enumerate_gadgets", args={"binary_path": "x"})
    )
    backend = GoogleBackend(model="gemini-pro-latest", client=_gemini_client(parts=[part]))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.tool_calls == [
        {"id": "enumerate_gadgets", "name": "enumerate_gadgets", "input": {"binary_path": "x"}}
    ]


def test_google_refusal_via_safety_finish_reason() -> None:
    part = SimpleNamespace(text="")
    backend = GoogleBackend(
        model="gemini-pro-latest", client=_gemini_client(parts=[part], finish="SAFETY")
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert backend.detect_refusal(resp)


def test_google_non_refusal_finish_reason() -> None:
    part = SimpleNamespace(text="working on it")
    backend = GoogleBackend(
        model="gemini-pro-latest", client=_gemini_client(parts=[part], finish="STOP")
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert not backend.detect_refusal(resp)


# --------------------------------------------------------------------------- #
# Message / schema translation (ADR 0011: valid provider wire formats)        #
# --------------------------------------------------------------------------- #


def test_anthropic_translates_tool_use_result_and_merges_users() -> None:
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="task"),
        # Consecutive user turn (the ADR-0011 baseline) must merge, not repeat.
        Message(role="user", content="Baseline gadget enumeration:\ng"),
        Message(
            role="assistant",
            content="calling",
            tool_calls=[{"id": "c1", "name": "enumerate_gadgets", "input": {"binary_path": "x"}}],
        ),
        Message(role="tool", content="gadgets", tool_call_id="c1"),
    ]
    api, system = _to_anthropic_messages(messages)
    assert system == "sys"
    # Two user text blocks merged into one leading user turn.
    assert api[0]["role"] == "user"
    assert [b["type"] for b in api[0]["content"]] == ["text", "text"]
    # Assistant tool call -> tool_use block.
    tool_use = next(b for b in api[1]["content"] if b["type"] == "tool_use")
    assert tool_use["id"] == "c1"
    assert tool_use["name"] == "enumerate_gadgets"
    assert tool_use["input"] == {"binary_path": "x"}
    # Tool message -> user turn with a tool_result keyed by the same id.
    assert api[2]["role"] == "user"
    assert api[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "c1",
        "content": "gadgets",
    }


def test_anthropic_no_system_returns_none() -> None:
    api, system = _to_anthropic_messages([Message(role="user", content="hi")])
    assert system is None
    assert api == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def _capturing_openai_client() -> tuple[Any, dict[str, Any]]:
    captured: dict[str, Any] = {}
    message = SimpleNamespace(content="ok", tool_calls=None)
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resp

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, captured


def test_openai_sends_max_completion_tokens_and_omits_sampling() -> None:
    # gpt-5 needs max_completion_tokens and rejects custom temperature/seed.
    client, captured = _capturing_openai_client()
    OpenAIBackend(model="gpt-5", client=client).chat(_MESSAGES, _TOOLS, 256)
    assert captured["max_completion_tokens"] == 256
    assert "max_tokens" not in captured
    assert "temperature" not in captured
    assert "seed" not in captured


def test_lmstudio_sends_legacy_max_tokens_and_sampling() -> None:
    client, captured = _capturing_openai_client()
    LMStudioBackend("m", BackendCategory.OPEN_WEIGHT, client=client).chat(_MESSAGES, _TOOLS, 256)
    assert captured["max_tokens"] == 256
    assert "max_completion_tokens" not in captured
    # Local models honor the determinism knobs.
    assert captured["temperature"] == 0.2
    assert captured["seed"] == 0


def _capturing_anthropic_client() -> tuple[Any, dict[str, Any]]:
    captured: dict[str, Any] = {}
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        model_dump=lambda: {"stop_reason": "end_turn"},
    )

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resp

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client, captured


def test_anthropic_sonnet_sends_temperature() -> None:
    from backends.anthropic_backend import AnthropicBackend

    client, captured = _capturing_anthropic_client()
    AnthropicBackend(model="claude-sonnet-4-6", client=client).chat(_MESSAGES, _TOOLS, 256)
    assert captured["temperature"] == 0.2
    assert captured["max_tokens"] == 256


def test_anthropic_opus_omits_deprecated_temperature() -> None:
    # claude-opus-4-7 400s if temperature is sent ("deprecated for this model"),
    # so the backend must omit it — mirrors the gpt-5 handling.
    from backends.anthropic_backend import AnthropicBackend

    client, captured = _capturing_anthropic_client()
    AnthropicBackend(model="claude-opus-4-7", client=client).chat(_MESSAGES, _TOOLS, 256)
    assert "temperature" not in captured
    assert captured["max_tokens"] == 256


# --- prompt caching (ADR 0023): stable-prefix cache_control -------------------- #


def test_anthropic_marks_system_and_tools_with_cache_control() -> None:
    from backends.anthropic_backend import AnthropicBackend

    client, captured = _capturing_anthropic_client()
    AnthropicBackend(model="claude-sonnet-4-6", client=client).chat(_MESSAGES, _TOOLS, 256)
    # System becomes a cached text block (the stable prefix).
    system = captured["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # The last tool carries the cache breakpoint (caches the whole tool schema).
    assert captured["tools"][-1]["cache_control"] == {"type": "ephemeral"}


def test_anthropic_cache_control_is_byte_stable_across_turns() -> None:
    # The cached prefix (system + tools) must be identical across reason turns for
    # the cache to hit; the same inputs produce the same marked request.
    from backends.anthropic_backend import AnthropicBackend

    c1, cap1 = _capturing_anthropic_client()
    c2, cap2 = _capturing_anthropic_client()
    AnthropicBackend(model="claude-sonnet-4-6", client=c1).chat(_MESSAGES, _TOOLS, 256)
    AnthropicBackend(model="claude-sonnet-4-6", client=c2).chat(_MESSAGES, _TOOLS, 256)
    assert cap1["system"] == cap2["system"]
    assert cap1["tools"] == cap2["tools"]


def test_anthropic_caching_can_be_disabled() -> None:
    from backends.anthropic_backend import AnthropicBackend

    client, captured = _capturing_anthropic_client()
    backend = AnthropicBackend(model="claude-sonnet-4-6", client=client)
    backend._prompt_cache = False
    backend.chat(_MESSAGES, _TOOLS, 256)
    assert isinstance(captured["system"], str)  # plain system, no cache blocks
    assert all("cache_control" not in t for t in captured["tools"])


def test_gemini_sanitize_strips_unsupported_schema_keys() -> None:
    schema = {
        "type": "object",
        "required": ["p"],
        "additionalProperties": False,
        "properties": {
            "p": {"type": "string", "description": "d"},
            "n": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
        },
    }
    out = _sanitize_schema(schema)
    assert "additionalProperties" not in out
    assert out["type"] == "object"
    assert out["required"] == ["p"]
    assert out["properties"]["p"] == {"type": "string", "description": "d"}
    # default / minimum / maximum are dropped (Gemini's Schema rejects them).
    assert out["properties"]["n"] == {"type": "integer"}


def test_gemini_contents_fold_system_and_merge_users() -> None:
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="task"),
        Message(role="user", content="Baseline gadget enumeration:\ng"),
        Message(role="assistant", content="ok"),
    ]
    contents = _to_gemini_contents(messages)
    assert len(contents) == 2  # merged user turn + model turn
    assert contents[0]["role"] == "user"
    assert [p["text"] for p in contents[0]["parts"]][0] == "sys"
    assert contents[1]["role"] == "model"
