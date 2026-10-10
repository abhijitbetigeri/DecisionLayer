"""One OpenAI-compatible client for every model, routed through the Respan gateway.

Respan gives three model families behind one key, which is what the simulator needs for a
diverse buyer-agent population. Model ids verified against the gateway on 2026-10-10.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

# Buyer-agent population: one model per family.
BUYER_MODELS = [
    "claude-haiku-4-5-20251001",
    "gpt-5-mini",
    "openrouter/google/gemini-2.5-flash",
]
# Stronger model for the guard and the fixer.
GUARD_MODEL = os.environ.get("SV_GUARD_MODEL", "claude-sonnet-5-5")


@lru_cache
def client() -> OpenAI:
    key = os.environ.get("RESPAN_API_KEY")
    base = os.environ.get("RESPAN_BASE_URL")
    if not key:
        creds = json.loads((Path.home() / ".respan" / "credentials.json").read_text())["default"]
        key, base = creds["apiKey"], base or creds["baseUrl"]
    # The stored base URL omits /api (the Respan CLI appends it), so add it here.
    return OpenAI(api_key=key, base_url=(base or "https://api.respan.ai").rstrip("/") + "/api")


def chat(model: str, messages: list[dict], **kw):
    return client().chat.completions.create(model=model, messages=messages, **kw)


def chat_json(model: str, system: str, user: str) -> dict:
    """Single-turn call that must return a JSON object."""
    resp = chat(model, [{"role": "system", "content": system}, {"role": "user", "content": user}])
    text = resp.choices[0].message.content or ""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])
