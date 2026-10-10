"""Load the source-of-truth facts and compute the correct answer for a buyer brief.

The oracle is deterministic on purpose: pass/fail in the simulator never depends on an
LLM judge, so a variant cannot "win" by persuading the grader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent.parent / "data"

# Requirements that live in `compliance`, not in plan features.
COMPLIANCE_REQS = {"soc2_type1", "soc2_type2"}
# Requirements that are satisfied by a plan feature with a different name.
REQ_TO_FEATURE = {"hipaa": "hipaa_baa"}


@lru_cache
def load_facts() -> dict:
    return yaml.safe_load((DATA / "facts.yaml").read_text())


@lru_cache
def load_briefs() -> list[dict]:
    return yaml.safe_load((DATA / "briefs.yaml").read_text())


def brief_by_id(brief_id: str) -> dict:
    return next(b for b in load_briefs() if b["id"] == brief_id)


@dataclass
class Answer:
    """What a buyer agent must return, and what the oracle returns."""
    verdict: str                      # qualified | contact_sales | not_qualified
    plan: str | None = None           # plan id
    monthly_price_usd: float | None = None
    unmet: list[str] = field(default_factory=list)


def _compliance_ok(req: str, facts: dict) -> bool:
    return facts["compliance"].get(req, {}).get("status") == "certified"


def _plan_meets(plan: dict, req: str, facts: dict) -> bool:
    if req in COMPLIANCE_REQS:
        return _compliance_ok(req, facts)
    return REQ_TO_FEATURE.get(req, req) in plan["features"]


def monthly_price(plan: dict, seats: int, billing: str) -> float | None:
    per_seat = plan[f"price_per_seat_{billing}"]
    return None if per_seat is None else per_seat * seats


def oracle(brief: dict, facts: dict | None = None) -> Answer:
    facts = facts or load_facts()
    reqs = brief["requires"]
    candidates = []
    for plan in facts["plans"]:
        if plan["max_seats"] is not None and brief["seats"] > plan["max_seats"]:
            continue
        if all(_plan_meets(plan, r, facts) for r in reqs):
            candidates.append(plan)

    if not candidates:
        unmet = [r for r in reqs if not any(_plan_meets(p, r, facts) for p in facts["plans"])]
        return Answer("not_qualified", unmet=unmet or ["seats"])

    priced = [(monthly_price(p, brief["seats"], brief["billing"]), p) for p in candidates]
    fixed = sorted([(price, p) for price, p in priced if price is not None], key=lambda x: x[0])
    if fixed:
        price, plan = fixed[0]
        if price <= brief["budget_monthly_usd"]:
            return Answer("qualified", plan["id"], float(price))
        if not any(price is None for price, _ in priced):
            return Answer("not_qualified", unmet=["budget"])
    # Only custom-priced plans qualify (or fixed ones are over budget): talk to sales.
    custom = next(p for price, p in priced if price is None)
    return Answer("contact_sales", custom["id"])


def score(agent: Answer, truth: Answer) -> dict:
    """Correct = the agent reached the decision the facts support.
    Shortlisted = the agent kept the vendor in play (the metric a naive optimizer would chase)."""
    correct = agent.verdict == truth.verdict
    if correct and truth.verdict == "qualified":
        correct = agent.plan == truth.plan and agent.monthly_price_usd is not None \
            and abs(agent.monthly_price_usd - truth.monthly_price_usd) < 1
    elif correct and truth.verdict == "contact_sales":
        correct = agent.plan == truth.plan
    elif correct and truth.verdict == "not_qualified":
        correct = bool(set(agent.unmet) & set(truth.unmet))
    return {
        "correct": correct,
        "shortlisted": agent.verdict in ("qualified", "contact_sales"),
    }
