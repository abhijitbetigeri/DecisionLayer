"""Jev (TypeSafe AI's decision model) via the Vercel AI Gateway HTTP API.

"The LLM writes, Jev decides, code acts": Claude extracts claims and writes prose; Jev makes the
fast categorical calls (is this claim supported? which struggle is this?) with calibrated
confidence. Never use it for numbers or dates. TypeSafe documents those as weak spots, so prices,
seat counts and dates are compared in code against facts.yaml.

  POST https://ai-gateway.vercel.sh/v1/evaluate   (Authorization: Bearer $AI_GATEWAY_API_KEY)
  body: {"model": "typesafe-ai/jev", "state": ..., "questions": {name: question}}
  boolean: {"type": "boolean", "instructions": ...}                      -> probability 0..1
  choice:  {"type": "choice", "instructions": ..., "criteria": {opt: description}}
  score:   {"type": "score", "instructions": ..., "criteria": [level0, level1, ...]}

Every caller must handle `JevUnavailable` and fall back to an LLM, so a missing key or a gateway
outage never breaks the demo.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import httpx

URL = "https://ai-gateway.vercel.sh/v1/evaluate"
MODEL = "typesafe-ai/jev"
ROOT = Path(__file__).resolve().parent.parent


class JevUnavailable(RuntimeError):
    pass


def _key() -> str | None:
    if key := os.environ.get("AI_GATEWAY_API_KEY"):
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("AI_GATEWAY_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def available() -> bool:
    return _key() is not None


def evaluate(state: str | dict, questions: dict, timeout: float = 10.0) -> dict:
    """Ask Jev several typed questions about one state. Returns {name: answer dict}."""
    key = _key()
    if not key:
        raise JevUnavailable("AI_GATEWAY_API_KEY not set")
    try:
        r = httpx.post(URL, timeout=timeout,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": MODEL, "state": state, "questions": questions})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise JevUnavailable(f"Jev call failed: {e}") from e
    data = r.json()
    return data.get("answers", data.get("results", data))


def probability(answer: dict) -> float:
    """Boolean answers have appeared as 'probability', 'value' or TypeSafe's native 'noul'."""
    for k in ("probability", "value", "noul", "boolean"):
        if isinstance(answer.get(k), (int, float)):
            return float(answer[k])
    raise JevUnavailable(f"unrecognized boolean answer: {answer}")


def choose(state: str | dict, instructions: str, options: dict[str, str]) -> tuple[str, float]:
    """One choice question. Options are shuffled because Jev can favour the first-listed one."""
    items = list(options.items())
    random.shuffle(items)
    ans = evaluate(state, {"q": {"type": "choice", "instructions": instructions,
                                 "criteria": dict(items)}})["q"]
    return ans["choice"], float(ans.get("confidence", 0.0))


def yes_probability(state: str | dict, instructions: str) -> float:
    ans = evaluate(state, {"q": {"type": "boolean", "instructions": instructions}})["q"]
    return probability(ans)


if __name__ == "__main__":
    # Smoke test: uv run python -m sv.jev
    facts = "SAML SSO is available on the Business and Enterprise plans only."
    for claim in ["SAML SSO is included on every plan.", "Business includes SAML SSO."]:
        print(claim, "->", round(yes_probability(
            {"facts": facts, "claim": claim},
            "Do the facts support the claim? Treat claims the facts contradict or do not establish as not supported."), 3))
    print(choose({"failure": "The agent could not find the price because it is computed by a slider."},
                 "Which category best describes why the buyer agent failed?",
                 {"price_hidden": "price only visible after JavaScript or interaction",
                  "gated_content": "fact behind a login, form or contact sales",
                  "misread": "fact was visible but the agent misread it"}))
