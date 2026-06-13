"""Unified LLM provider for MuleNet AI (P5).

Same OpenAI-SDK method OpenRouter documents — only the base_url differs — with the provider
**auto-detected from the API key** so a valid key always reaches the service that accepts it:

  - key starts 'sk-or-'  -> OpenRouter (https://openrouter.ai/api/v1), model from OPENROUTER_MODEL,
                            reasoning enabled (extra_body={"reasoning": {"enabled": True}}).
  - key starts 'sk-'     -> OpenAI (https://api.openai.com/v1), model from OPENAI_MODEL.
                            (OpenRouter rejects non 'sk-or-' keys with 401, so an OpenAI key must
                            go to OpenAI — that's where it's valid.)

    from openai import OpenAI
    client = OpenAI(base_url=<base>, api_key=<key>)
    client.chat.completions.create(model=<model>, messages=..., extra_body=...)

The key is read from the environment (loaded from the gitignored `.env` by backend/ai/__init__.py),
so it is never committed. With no key, callers fall back to deterministic templates.
"""
from __future__ import annotations

import os

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def _config() -> tuple[str, str, str, bool] | None:
    """(label, base_url, model, reasoning) for the provider the key belongs to, or None."""
    key = api_key()
    if not key:
        return None
    if key.startswith("sk-or-"):
        model = os.getenv("OPENROUTER_MODEL") or os.getenv("MULENET_MODEL") or DEFAULT_OPENROUTER_MODEL
        return "openrouter", OPENROUTER_BASE, model, True
    # sk-proj-… / sk-… are OpenAI keys (OpenRouter 401s on them) -> send to OpenAI.
    return "openai", OPENAI_BASE, (os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL), False


def available() -> bool:
    return _config() is not None


def provider() -> str:
    cfg = _config()
    return cfg[0] if cfg else "none"


def model() -> str:
    cfg = _config()
    return cfg[2] if cfg else ""


def _reasoning_enabled() -> bool:
    return os.getenv("OPENROUTER_REASONING", "1") != "0"


def _client(base_url: str):
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key())


def complete(messages: list[dict], max_tokens: int = 800, tools: list | None = None,
             temperature: float | None = None) -> dict:
    """One chat completion via the OpenAI SDK against the auto-detected provider. Returns the
    assistant message normalized to a dict (role/content[/tool_calls][/reasoning_details]) plus
    '_source'. Raises on API errors so callers can fall back.

    Pass temperature (e.g. 0.8) for varied, non-deterministic output."""
    cfg = _config()
    if not cfg:
        raise RuntimeError("no API key configured")
    label, base, mdl, reasoning = cfg
    client = _client(base)
    kwargs: dict = {"model": mdl, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if reasoning and _reasoning_enabled():  # OpenRouter only; OpenAI rejects unknown fields
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
    out["_source"] = label
    return out


def text(messages: list[dict], max_tokens: int = 800, temperature: float | None = None) -> tuple[str, str]:
    """Convenience for one-shot text generation. Returns (content, source)."""
    msg = complete(messages, max_tokens=max_tokens, temperature=temperature)
    return (msg.get("content") or ""), msg.get("_source", provider())


def bad_key_hint() -> str:
    """Guidance when the key matches no known provider format (neither sk-or- nor sk-)."""
    k = api_key()
    if k and not (k.startswith("sk-or-") or k.startswith("sk-")):
        return (" — the key doesn't look like an OpenRouter (sk-or-v1-…) or OpenAI (sk-…) key. "
                "Check OPENROUTER_API_KEY in .env.")
    return ""
