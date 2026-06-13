"""Unified LLM provider for MuleNet AI (P5).

**For now: OpenRouter only**, via the OpenAI SDK pointed at OpenRouter's base URL, with
reasoning enabled — exactly the structure in OpenRouter's docs:

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key="<OPENROUTER_API_KEY>")
    client.chat.completions.create(model=..., messages=..., extra_body={"reasoning": {"enabled": True}})

The API key is read from the environment (loaded from the gitignored `.env` by backend/ai/__init__.py),
so it is never committed. With no key, callers fall back to deterministic templates.
"""
from __future__ import annotations

import os

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


def api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def model() -> str:
    """OpenRouter model slug. OPENROUTER_MODEL wins, then MULENET_MODEL, then the nvidia default."""
    return os.getenv("OPENROUTER_MODEL") or os.getenv("MULENET_MODEL") or DEFAULT_MODEL


def available() -> bool:
    return bool(api_key())


def provider() -> str:
    return "openrouter" if available() else "none"


def _reasoning_enabled() -> bool:
    return os.getenv("OPENROUTER_REASONING", "1") != "0"


def _client():
    from openai import OpenAI
    return OpenAI(base_url=OPENROUTER_BASE, api_key=api_key())


def complete(messages: list[dict], max_tokens: int = 800, tools: list | None = None) -> dict:
    """One OpenRouter chat completion via the OpenAI SDK. Returns the assistant message normalized
    to a dict (role/content[/tool_calls][/reasoning_details]) plus '_source'. Raises on API errors."""
    client = _client()
    kwargs: dict = {"model": model(), "messages": messages, "max_tokens": max_tokens}
    if _reasoning_enabled():
        kwargs["extra_body"] = {"reasoning": {"enabled": True}}
    if tools:
        kwargs["tools"] = tools
    resp = client.chat.completions.create(**kwargs)
    m = resp.choices[0].message
    out: dict = {"role": "assistant", "content": m.content or ""}
    if getattr(m, "tool_calls", None):
        out["tool_calls"] = [{"id": tc.id, "type": "function",
                              "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                             for tc in m.tool_calls]
    rd = getattr(m, "reasoning_details", None)
    if rd is not None:
        out["reasoning_details"] = rd  # pass back unmodified so the model continues its reasoning
    out["_source"] = "openrouter"
    return out


def text(messages: list[dict], max_tokens: int = 800) -> tuple[str, str]:
    """Convenience for one-shot text generation. Returns (content, 'openrouter')."""
    msg = complete(messages, max_tokens=max_tokens)
    return (msg.get("content") or ""), "openrouter"


def bad_key_hint() -> str:
    """Plain guidance when the configured key isn't an OpenRouter key (OpenRouter keys are sk-or-v1-…)."""
    k = api_key()
    if k and not k.startswith("sk-or-"):
        return (f" — your key starts with '{k[:7]}…', but OpenRouter keys begin with 'sk-or-v1-'. "
                "Create one at https://openrouter.ai/keys and put it in .env.")
    return ""
