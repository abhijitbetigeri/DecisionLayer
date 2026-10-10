"""A buyer agent: carries a brief, reads the vendor site, returns a structured decision.

Fetch mode only for now (no JS), via an in-process client, so no server is needed to
simulate. A Playwright browser mode can be added behind the same `open_url` tool.
"""
from __future__ import annotations

import json
from urllib.parse import urljoin

from fastapi.testclient import TestClient

from sv import llm
from sv.events import EventLog
from sv.facts import Answer, load_facts
from sv.simulator.pagetext import page_to_text
from sv.site.app import app

MAX_STEPS = 10
_site = TestClient(app)

TOOLS = [
    {"type": "function", "function": {
        "name": "open_url",
        "description": "Fetch a page on the vendor's website and return its readable text.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "submit_answer",
        "description": "Submit your final decision about this vendor. Call exactly once.",
        "parameters": {"type": "object", "properties": {
            "verdict": {"type": "string", "enum": ["qualified", "contact_sales", "not_qualified"]},
            "plan": {"type": ["string", "null"], "description": "Plan name in lowercase, e.g. 'team'"},
            "monthly_price_usd": {"type": ["number", "null"],
                                  "description": "Total USD per month for the brief's seats and billing"},
            "unmet": {"type": "array", "items": {"type": "string"},
                      "description": "Requirement keys that are unmet or could not be verified"},
            "notes": {"type": "string"}},
            "required": ["verdict", "unmet"]}}},
]

SYSTEM = """You are a procurement agent acting for a buyer. You are evaluating one vendor, {vendor},
by reading its website only. Start at {start}. You have at most {max_steps} tool calls.

Buyer brief:
{brief}

Decide one verdict:
- qualified: a plan with published pricing meets every requirement, fits the seat count, and its
  total monthly cost for the brief's seats and billing period is within budget. Give plan and price.
- contact_sales: requirements are met only by a plan with custom pricing. Give the plan.
- not_qualified: no plan meets the requirements, or the cost exceeds budget. List unmet keys
  (use the requirement keys from the brief, or "budget").

Rules: only trust what the website states. If you cannot verify a requirement from the website,
treat it as unmet. Monthly price means total USD per month for all seats on the brief's billing period.
When you are done, call submit_answer."""


def _plan_id(name: str | None) -> str | None:
    """Agents write 'Business plan', 'Business', 'business'; map all to the plan id."""
    if not name:
        return None
    lowered = name.lower()
    return next((p["id"] for p in load_facts()["plans"] if p["id"] in lowered), lowered)


def run_agent(*, run_id: str, variant: str, brief: dict, model: str, log: EventLog) -> tuple[Answer | None, int]:
    start = f"/{variant}/"
    brief_view = {k: v for k, v in brief.items() if k != "id"}
    messages = [
        {"role": "system", "content": SYSTEM.format(vendor="Pulse", start=start, max_steps=MAX_STEPS,
                                                    brief=json.dumps(brief_view, indent=2))},
        {"role": "user", "content": "Evaluate Pulse against the brief and submit your answer."},
    ]
    current = start
    for n in range(1, MAX_STEPS + 1):
        resp = llm.chat(model, messages, tools=TOOLS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({"role": "user", "content": "Use a tool: open_url or submit_answer."})
            continue
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if tc.function.name == "submit_answer":
                log.emit("step", run_id=run_id, n=n, tool="submit_answer", arg=args, note="")
                return Answer(verdict=args.get("verdict", "not_qualified"),
                              plan=_plan_id(args.get("plan")),
                              monthly_price_usd=args.get("monthly_price_usd"),
                              unmet=args.get("unmet") or []), n
            url = urljoin(f"http://pulse.test{current}", args.get("url", start))
            path = url.replace("http://pulse.test", "")
            r = _site.get(path)
            text = page_to_text(r.text) if r.status_code == 200 else f"HTTP {r.status_code}"
            if r.headers.get("content-type", "").startswith("text/plain"):
                text = r.text
            current = path
            log.emit("step", run_id=run_id, n=n, tool="open_url", arg=path, note=f"HTTP {r.status_code}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
    return None, MAX_STEPS
