"""Tag each failed run with a named "agent struggle" (Introspection-style), so failures roll
up into a short ranked list the fixer can act on instead of a pile of traces."""
from __future__ import annotations

import json

from sv import llm
from sv.events import EventLog, read

CATEGORIES = {
    "price_hidden": "price only computable with JavaScript or interaction, not stated in text",
    "requirement_unstated": "a required fact (feature, compliance, region) is not stated anywhere the agent read",
    "gated_content": "the fact sits behind a login, form or 'contact sales'",
    "vague_wording": "the page uses marketing wording that does not map to the requirement",
    "misread": "the fact was on the page but the agent misread or miscalculated it",
    "other": "anything else",
}

SYSTEM = ("You diagnose why a buyer agent reached the wrong decision about a vendor website. "
          "Pick the single best category and explain in one sentence, citing the page. "
          'Return JSON: {"category": "...", "detail": "..."}. Categories:\n'
          + "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items()))


def diagnose_run(run_id: str, log: EventLog) -> dict:
    events = [e for e in read(log.path) if e.get("run_id") == run_id]
    finished = next(e for e in events if e["type"] == "run_finished")
    steps = [f"{e['tool']} {e['arg']} ({e['note']})" for e in events if e["type"] == "step"]
    user = json.dumps({"pages_visited": steps, "agent_answer": finished["answer"],
                       "correct_answer": finished["truth"]}, indent=2)
    try:
        out = llm.chat_json(llm.GUARD_MODEL, SYSTEM, user)
    except Exception as e:
        out = {"category": "other", "detail": f"diagnosis failed: {e}"[:200]}
    if out.get("category") not in CATEGORIES:
        out["category"] = "other"
    log.emit("struggle", run_id=run_id, variant=finished["variant"], **out)
    return out
