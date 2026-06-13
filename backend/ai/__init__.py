"""backend.ai — AI layer (P5).

Side effect on import: load a repo-root ``.env`` into the environment so the SAR generator
and the "Ask MuleNet" copilot pick up their API keys (OPENROUTER_API_KEY / ANTHROPIC_API_KEY /
MULENET_MODEL) without anyone having to export them by hand. Dependency-free (no python-dotenv);
already-set environment variables always win over the file.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:  # never override a real env var
            os.environ[key] = val


_load_dotenv()
