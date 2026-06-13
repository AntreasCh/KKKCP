"""Unified LLM provider for MuleNet AI (P5).

Auto-detects the provider from the API key so the *same* key variable works everywhere:
  - key starts 'sk-or-'  -> OpenRouter (OpenAI-compatible); model from OPENROUTER_MODEL
  - key starts 'sk-'     -> OpenAI;       model from OPENAI_MODEL (default gpt-4o-mini)

Both speak the OpenAI Chat Completions API, so one HTTP path serves both. The key may be
supplied via OPENROUTER_API_KEY or OPENAI_API_KEY (whichever is set). Anthropic stays separate
(handled directly in copilot.py / sar.py). With no usable key, callers fall back to templates.
"""
from __future__ import annotations

import os

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def provider() -> str:
    """'openrouter' | 'openai' | 'none', decided by the key prefix."""
    k = api_key()
    if k.startswith("sk-or-"):
        return "openrouter"
    if k.startswith("sk-"):  # sk-proj-… / sk-… are OpenAI
        return "openai"
    return "none"


def _config() -> tuple[str, str] | None:
    """(base_url, model) for the active OpenAI-compatible provider, or None if no usable key."""
    p = provider()
    if p == "openrouter":
        return OPENROUTER_BASE, (os.getenv("OPENROUTER_MODEL") or os.getenv("MULENET_MODEL")
                                 or DEFAULT_OPENROUTER_MODEL)
    if p == "openai":
        return OPENAI_BASE, (os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
    return None


def available() -> bool:
    return _config() is not None


def _headers(base: str) -> dict:
    h = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}
    if "openrouter" in base:  # optional ranking headers per OpenRouter docs
        h["HTTP-Referer"] = "http://localhost:8000"
        h["X-Title"] = "MuleNet"
    return h


def complete(messages: list[dict], max_tokens: int = 800, tools: list | None = None) -> dict:
    """One Chat Completions call. Returns the assistant message dict (OpenAI shape) with an extra
    '_source' key. Raises on HTTP/auth errors so callers can fall back."""
    import httpx

    cfg = _config()
    if not cfg:
        raise RuntimeError("no OpenAI-compatible API key configured")
    base, model = cfg
    payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
    # OpenRouter reasoning tokens (the `extra_body={"reasoning":{"enabled":True}}` from their docs is
    # just this top-level field). On by default for OpenRouter; set OPENROUTER_REASONING=0 to disable.
    if "openrouter" in base and os.getenv("OPENROUTER_REASONING", "1") != "0":
        payload["reasoning"] = {"enabled": True}
    r = httpx.post(f"{base}/chat/completions", headers=_headers(base), json=payload, timeout=120)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    msg["_source"] = provider()
    return msg


def text(messages: list[dict], max_tokens: int = 800) -> tuple[str, str]:
    """Convenience for one-shot text generation. Returns (content, source)."""
    msg = complete(messages, max_tokens=max_tokens)
    return (msg.get("content") or ""), msg.get("_source", provider())


def bad_key_hint() -> str:
    """Plain guidance when a configured key matches no known provider format."""
    k = api_key()
    if k and not (k.startswith("sk-or-") or k.startswith("sk-")):
        return (" — the API key doesn't look like an OpenRouter (sk-or-v1-…) or OpenAI (sk-…) key. "
                "Check OPENROUTER_API_KEY in .env.")
    return ""
