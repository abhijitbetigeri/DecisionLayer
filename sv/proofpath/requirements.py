"""Buyer brief → validated requirement list (WS1).

Models only *propose* requirement keys; everything is validated against the allowlist in
shared-truth §2. Unknown keys are dropped and reported in `dropped_terms`. Model chain:
Gemma 4 31B → Kimi K2 → preset fallback (parsed_by="preset"). PROOFPATH_ENABLE_LLM=0 skips models.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import os
from typing import Any, Optional

from sv.proofpath.contracts import REQUIREMENT_KEYS, BriefVersion, Persona, Requirement
from sv.proofpath.fixtures import DEMO_BRIEF, PRESETS, SYSTEMS

log = logging.getLogger("decision_layer.requirements")

MODELS = ("openrouter/google/gemma-4-31b-it", "openrouter/moonshotai/kimi-k2")
MODEL_TIMEOUT_S = float(os.environ.get("PROOFPATH_LLM_TIMEOUT", "25"))

REQUIREMENT_META = {
    "eu_hosting": ("EU deployment", "capability",
                   "Documented EU deployment option on a purchasable plan"),
    "us_hosting": ("US deployment", "capability", "Documented US deployment option"),
    "sso": ("Single sign-on (SAML)", "capability", "Documented SAML SSO on a purchasable plan"),
    "recovery_demonstrated": ("Failed syncs recover without duplicates (demonstrated)", "demonstration",
                              "Passing crm_warehouse_sync/v1 run linked to this brief version; "
                              "documented support alone is not enough"),
    "idempotent_delivery": ("No duplicate records on retry (documented)", "capability",
                            "Documented idempotent delivery or a passing POC"),
    "budget_monthly_usd": ("Monthly budget ceiling", "constraint",
                           "Cheapest plan meeting all capability requirements has a known price at or "
                           "below the ceiling; a quote-only plan is unknown"),
}

SYSTEM_PROMPT = f"""You convert an enterprise software buyer's brief into candidate requirements.
Return ONLY a JSON object:
{{"goal": "<one sentence>", "systems": ["<system (role)>", ...],
  "requirements": [{{"key": "<key>", "hard": true|false, "expected": <number or null>}}]}}
Allowed keys (use no others; put anything else under "unrecognized" as plain strings):
- eu_hosting: EU deployment / data residency
- us_hosting: US deployment
- sso: single sign-on (SAML)
- recovery_demonstrated: failed syncs must recover without duplicates (the buyer needs it to work)
- idempotent_delivery: no duplicate records on retry, documented (optional, soft)
- budget_monthly_usd: monthly budget ceiling in USD as "expected"
"hard" = the buyer says it is required. Nice-to-haves are hard=false.
Also return "unrecognized": [..] listing ONLY requested capabilities, certifications or constraints that
are outside the allowed keys, each as a short noun phrase (e.g. "HIPAA compliance", "on-premise
deployment", "SCIM provisioning", "99.99% uptime SLA").
NEVER put these in "unrecognized": the workflow or goal ("sync NetSuite invoices into Snowflake"),
systems or data objects ("HubSpot deals", "Snowflake destination"), schedules or frequency ("nightly",
"each night"), team size, or anything already covered by an allowed key. Use [] when nothing is left."""


def input_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def llm_enabled() -> bool:
    return os.environ.get("PROOFPATH_ENABLE_LLM", "1") != "0"


def make_requirement(key: str, hard: bool, weight: Optional[float] = None, expected: Any = None,
                     id_: Optional[str] = None) -> Requirement:
    label, _, criteria = REQUIREMENT_META[key]
    kw = {"id": id_} if id_ else {}
    soft_weight = 1.0 if weight is None else max(0.0, float(weight))
    return Requirement(key=key, label=label, hard=bool(hard), weight=0.0 if hard else soft_weight,
                       expected=expected, acceptance_criteria=criteria, **kw)


def preset_brief(preset_id: str, evaluation_id: str, *, input_text: str = "") -> BriefVersion:
    p = PRESETS[preset_id]
    reqs = [make_requirement(r["key"], r["hard"], r.get("weight"), r.get("expected")) for r in p["requirements"]]
    return BriefVersion(evaluation_id=evaluation_id, version=0, goal=p["goal"], systems=list(p["systems"]),
                        requirements=reqs, parsed_by="preset",
                        input_hash=input_hash(input_text or p["brief_text"]))


def infer_preset(text: str) -> str:
    """Deterministic preset choice when no preset id is given and models are unavailable."""
    t = text.lower()
    if "$" in t or "budget" in t or "per month" in t:
        return "strict_budget"
    if ("us" in t.split() or "united states" in t or "us-" in t) and "eu" not in t:
        return "us_operations"
    return "eu_technical"


def preset_for_brief(brief: BriefVersion, preset_id: Optional[str] = None) -> str:
    """Preset whose preference rubric applies to a brief (explicit id wins)."""
    if preset_id in PRESETS:
        return preset_id
    keys = {r.key for r in brief.requirements}
    if "budget_monthly_usd" in keys:
        return "strict_budget"
    if "us_hosting" in keys and "eu_hosting" not in keys:
        return "us_operations"
    return "eu_technical"


def validate_proposal(data: Any) -> tuple[list[Requirement], list[str], str, list[str]]:
    """Validate a model proposal. Returns (requirements, dropped_terms, goal, systems)."""
    if not isinstance(data, dict):
        raise ValueError("proposal is not an object")
    reqs: list[Requirement] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in data.get("requirements") or []:
        key = item.get("key") if isinstance(item, dict) else item
        if not isinstance(key, str):
            continue
        key = key.strip()
        if key not in REQUIREMENT_KEYS:
            dropped.append(key)
            continue
        if key in seen:
            continue
        seen.add(key)
        hard = bool(item.get("hard", True)) if isinstance(item, dict) else True
        expected = item.get("expected") if isinstance(item, dict) else None
        if key == "budget_monthly_usd":
            try:
                expected = float(expected)
            except (TypeError, ValueError):
                dropped.append("budget_monthly_usd (no numeric ceiling)")
                seen.discard(key)
                continue
        else:
            expected = None
        reqs.append(make_requirement(key, hard, 1.0, expected))
    for term in data.get("unrecognized") or []:
        if isinstance(term, str) and term.strip():
            dropped.append(term.strip()[:80])
    if not reqs:
        raise ValueError("no allowlisted requirements")
    goal = data.get("goal") if isinstance(data.get("goal"), str) and data.get("goal").strip() else ""
    systems = [s for s in (data.get("systems") or []) if isinstance(s, str) and s.strip()][:6]
    return reqs, dropped, goal.strip()[:200], systems


def _call_model(model: str, text: str) -> dict:
    from sv.llm import chat_json
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(chat_json, model, SYSTEM_PROMPT, text)
        try:
            return fut.result(timeout=MODEL_TIMEOUT_S)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


def parse_brief(text: str, evaluation_id: str, preset_id: str | None) -> BriefVersion:
    """Unconfirmed brief. The app stores it with repo.append_brief."""
    text = (text or "").strip()
    if text and llm_enabled():
        for model in MODELS:
            try:
                reqs, dropped, goal, systems = validate_proposal(_call_model(model, text))
            except Exception as e:                       # invalid or unavailable → next in chain
                log.warning("brief parse with %s failed: %s", model, e)
                continue
            return BriefVersion(evaluation_id=evaluation_id, version=0, goal=goal or text[:200],
                                systems=systems or list(SYSTEMS), requirements=reqs, parsed_by=model,
                                input_hash=input_hash(text), dropped_terms=dropped)
    pid = preset_id if preset_id in PRESETS else infer_preset(text or DEMO_BRIEF)
    return preset_brief(pid, evaluation_id, input_text=text)


def edit_brief(repo, evaluation_id: str, body: dict) -> BriefVersion:
    """New brief version from a manual edit; optimistic concurrency via expected_version."""
    reqs: list[Requirement] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for r in body.get("requirements") or []:
        key = (r or {}).get("key")
        if key not in REQUIREMENT_KEYS or key in seen:
            dropped.append(str(key))
            continue
        seen.add(key)
        expected = r.get("expected")
        if key == "budget_monthly_usd":
            try:
                expected = float(expected)
            except (TypeError, ValueError):
                expected = None
        reqs.append(make_requirement(key, bool(r.get("hard", True)), r.get("weight"),
                                     expected, id_=r.get("id")))
    try:
        persona = Persona(body.get("persona") or "technical")
    except ValueError:
        persona = Persona.technical
    brief = BriefVersion(evaluation_id=evaluation_id, version=0, goal=body.get("goal") or "",
                         systems=list(body.get("systems") or []), persona=persona, requirements=reqs,
                         parsed_by="manual", input_hash=None, dropped_terms=dropped)
    return repo.append_brief(brief, expected_version=body.get("expected_version"))


def confirm(repo, brief_version_id: str):
    """Confirm a brief and build its comparison in one transaction (app does the same in steps)."""
    from sv.proofpath import evaluation
    with repo.transaction():
        brief = repo.confirm_brief(brief_version_id)
        snapshot = evaluation.recompute(repo, brief.evaluation_id)
    return brief, snapshot
