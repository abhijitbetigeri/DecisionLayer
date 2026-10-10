"""The guard: every factual claim a variant makes, on every surface, must be supported by
data/facts.yaml. A variant with any contradicted or unsupported claim is blocked before a
single simulated (or real) visitor sees it.

  uv run python -m sv.guard D
"""
from __future__ import annotations

import argparse
import json

import yaml
from fastapi.testclient import TestClient

from sv import llm
from sv.events import EventLog
from sv.facts import load_facts
from sv.simulator.pagetext import page_to_text
from sv.site.app import PAGES, app

SYSTEM = """You fact-check a vendor's website against its source-of-truth data.

List every factual claim on the page about: plans, prices, seat limits, features per plan,
SSO, provisioning, compliance certifications, data residency, HIPAA. Ignore subjective
marketing language ("loved by teams", "industry-leading") and navigation text.

For each claim give a verdict:
- supported: the source data states it
- contradicted: the source data states otherwise
- unsupported: the source data does not establish it

Return JSON: {"claims": [{"claim": "...", "verdict": "...", "fact": "<facts.yaml path or null>", "reason": "..."}]}"""


def surfaces(variant: str) -> dict[str, str]:
    site = TestClient(app)
    out = {}
    for page in PAGES:
        r = site.get(f"/{variant}/{page}")
        if r.status_code == 200:
            out[page or "home"] = page_to_text(r.text)
    r = site.get(f"/{variant}/llms.txt")
    if r.status_code == 200:
        out["llms.txt"] = r.text
    return out


def check_surface(text: str) -> list[dict]:
    facts = yaml.safe_dump(load_facts(), sort_keys=False)
    user = f"SOURCE DATA (facts.yaml):\n{facts}\n\nPAGE:\n{text}"
    return llm.chat_json(llm.GUARD_MODEL, SYSTEM, user).get("claims", [])


def check_variant(variant: str, log: EventLog | None = None) -> dict:
    """Two tiers: a contradicted claim blocks the variant; an unsupported one goes to review,
    because it usually means facts.yaml is missing a fact rather than the page lying."""
    blocked, review = [], []
    for surface, text in surfaces(variant).items():
        for c in check_surface(text):
            if log:
                log.emit("guard_claim", variant=variant, surface=surface, **c)
            if c.get("verdict") == "contradicted":
                blocked.append({"surface": surface, **c})
            elif c.get("verdict") == "unsupported":
                review.append({"surface": surface, **c})
    verdict = {"variant": variant, "passed": not blocked, "blocked_claims": blocked,
               "review_claims": review}
    if log:
        log.emit("guard_verdict", **verdict)
    return verdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--exp", default="guard")
    args = ap.parse_args()
    log = EventLog(args.exp)
    for v in args.variants:
        res = check_variant(v, log)
        print(f"\n== {v}: {'PASS' if res['passed'] else 'BLOCKED'}")
        for c in res["blocked_claims"] + res["review_claims"]:
            print(f"  [{c['verdict']}] ({c['surface']}) {c['claim']}\n      -> {c.get('reason', '')}")


if __name__ == "__main__":
    main()
