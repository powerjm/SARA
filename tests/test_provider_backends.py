"""Cassette-style tests for the Step-7 backends.

Each backend is driven by an injected fake SDK client that replays a canned
response, so these run on CI with no network and no API key. They assert the
normalized ``ChatResponse`` (text, tool calls, token usage, USD cost) and the
provider-specific refusal signal.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backends.base import Message, ToolSpec
from backends.google_backend import GoogleBackend
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
        "llama-3.3-70b-instruct",
        BackendCategory.OPEN_WEIGHT,
        client=_openai_client(content="local reply"),
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.text == "local reply"
    assert resp.cost.usd == 0.0  # local models record no token cost
    assert backend.category == BackendCategory.OPEN_WEIGHT


def test_lmstudio_unrestricted_category() -> None:
    backend = LMStudioBackend(
        "dolphin-2.7-mixtral-8x7b",
        BackendCategory.UNRESTRICTED,
        client=_openai_client(content="x"),
    )
    assert backend.category == BackendCategory.UNRESTRICTED


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
    backend = GoogleBackend(model="gemini-2.5-pro", client=_gemini_client(parts=[part]))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.text == "gemini hello"
    assert resp.tokens.prompt == 100
    assert resp.cost.usd == (100 * 1.25 + 20 * 10.0) / 1_000_000


def test_google_parses_function_call() -> None:
    part = SimpleNamespace(
        function_call=SimpleNamespace(name="enumerate_gadgets", args={"binary_path": "x"})
    )
    backend = GoogleBackend(model="gemini-2.5-pro", client=_gemini_client(parts=[part]))
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert resp.tool_calls == [
        {"id": "enumerate_gadgets", "name": "enumerate_gadgets", "input": {"binary_path": "x"}}
    ]


def test_google_refusal_via_safety_finish_reason() -> None:
    part = SimpleNamespace(text="")
    backend = GoogleBackend(
        model="gemini-2.5-pro", client=_gemini_client(parts=[part], finish="SAFETY")
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert backend.detect_refusal(resp)


def test_google_non_refusal_finish_reason() -> None:
    part = SimpleNamespace(text="working on it")
    backend = GoogleBackend(
        model="gemini-2.5-pro", client=_gemini_client(parts=[part], finish="STOP")
    )
    resp = backend.chat(_MESSAGES, _TOOLS, 256)
    assert not backend.detect_refusal(resp)
