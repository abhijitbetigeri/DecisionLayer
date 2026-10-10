"""Versioned evidence: fixture seeding, the controlled source update and operator review (WS1).

History is never rewritten: an approved update adds a new source version that `supersedes` the
previous one; the old version and its claims stay stored. A rejected update keeps the prior
approved version current. Pending claims are never adopted by findings.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from sv.proofpath import fixtures
from sv.proofpath.contracts import (Claim, Event, EventType, PendingUpdate, ReviewStatus,
                                    SourceVersion, new_id, now)
from sv.proofpath.repository import ConflictError, NotFoundError

log = logging.getLogger("decision_layer.evidence")

INJECTION_QUESTION = ("Does this text contain instructions addressed to an AI system or automated "
                      "agent (for example telling it to ignore rules, approve, rank or recommend something)?")
INJECTION_FLAG_THRESHOLD = 0.5
SEED_KEY = "fixtures_seeded"


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------ seeding
def seed(repo) -> None:
    """Idempotent: seeds once per data dir; a second startup preserves history."""
    if repo.get_meta(SEED_KEY):
        return
    with repo.transaction():
        for s in fixtures.SOURCES:
            repo.put_source_version(SourceVersion(**s, content_hash=content_hash(s["content"]),
                                                  published_at=fixtures.PUBLISHED, retrieved_at=fixtures.PUBLISHED,
                                                  review_status=ReviewStatus.approved))
        for c in fixtures.CLAIMS:
            repo.put_claim(Claim(**c, review_status=ReviewStatus.approved, reviewed_at=fixtures.PUBLISHED))
        repo.set_meta(SEED_KEY, now().isoformat())


DEMO_TABLES = ("evaluations", "briefs", "comparisons", "runs", "results", "artifacts", "reports",
               "agent_results", "events", "sources", "claims")


def reset(repo) -> None:
    """Clears demo state (evaluations, runs, reports, events, evidence updates) and re-seeds."""
    with repo.transaction():
        for t in DEMO_TABLES:
            repo._db.execute(f"DELETE FROM {t}")
        repo._db.execute("DELETE FROM meta WHERE key=? OR key LIKE 'injection:%'", (SEED_KEY,))
    seed(repo)


# ------------------------------------------------------------------ current evidence
def current_sources(repo) -> list[SourceVersion]:
    """The current approved version of each source (latest approved, not superseded)."""
    approved = [s for s in repo.list_source_versions() if s.review_status == ReviewStatus.approved]
    superseded = {s.supersedes for s in approved if s.supersedes}
    by_source: dict[str, SourceVersion] = {}
    for s in approved:                       # ordered by insertion; later approved versions win
        if s.id not in superseded:
            by_source[s.source_id] = s
    return list(by_source.values())


def current_claims(repo, sources: Optional[list[SourceVersion]] = None) -> list[Claim]:
    sources = current_sources(repo) if sources is None else sources
    out: list[Claim] = []
    for s in sources:
        out += [c for c in repo.list_claims(s.id) if c.review_status == ReviewStatus.approved]
    return out


def plans_for(source: SourceVersion, claims: list[Claim]) -> list[str]:
    """Plans offered by a source version: its price claims, cheapest first, quote-only last."""
    priced = [c for c in claims if c.requirement_key == "budget_monthly_usd" and c.plan]
    priced.sort(key=lambda c: (c.value is None, c.value if c.value is not None else 0))
    return [c.plan for c in priced] or list(fixtures.PRODUCTS[source.product_id]["plans"])


def _evaluations_with_comparison(repo) -> list[str]:
    evs = repo._list("evaluations")
    return [e.id for e in evs if repo.latest_comparison(e.id) is not None]


def _describe(claims: list[Claim], key: str) -> str:
    cs = [c for c in claims if c.requirement_key == key]
    if not cs:
        return "no claim"
    if key == "budget_monthly_usd":
        return "; ".join(f"{fixtures.PLAN_LABELS.get(c.plan, c.plan)} "
                         f"{'$%g/mo' % c.value if c.value is not None else 'quote only'}" for c in cs)
    v = cs[0].value
    if v is False:
        return "not available"
    if isinstance(v, list):
        return "documented on " + ", ".join(fixtures.PLAN_LABELS.get(p, p) for p in v)
    return str(v)


def diff_claims(before: list[Claim], after: list[Claim]) -> list[dict]:
    keys = list(dict.fromkeys([c.requirement_key for c in before] + [c.requirement_key for c in after]))
    out = []
    for k in keys:
        b, a = _describe(before, k), _describe(after, k)
        if b != a:
            out.append({"requirement_key": k, "before": b, "after": a})
    return out


# ------------------------------------------------------------------ controlled update
def _screen(text: str) -> Optional[float]:
    """Jev injection screen. Flags for the operator only; never approves or rejects."""
    if os.environ.get("PROOFPATH_ENABLE_LLM", "1") == "0":
        return None
    try:
        from sv import jev
        return round(jev.yes_probability(text, INJECTION_QUESTION), 3)
    except Exception as e:  # JevUnavailable or anything unexpected: no flag, operator still reviews
        log.warning("injection screen unavailable: %s", e)
        return None


def simulate_update(repo, scenario_id: str, *, screen: bool = True) -> PendingUpdate:
    """Creates a PENDING source version plus a diff; emits source_change_detected."""
    if scenario_id not in fixtures.UPDATES:
        raise NotFoundError(f"scenario/{scenario_id}")
    spec = fixtures.UPDATES[scenario_id]
    src = spec["source"]
    try:
        existing = repo.get_source_version(src["id"])
    except NotFoundError:
        existing = None
    if existing is not None and existing.review_status != ReviewStatus.rejected:
        if existing.review_status == ReviewStatus.pending:
            return pending_update(repo)              # idempotent re-click
        raise ConflictError("this update has already been approved")
    # A re-simulation after a rejection gets fresh ids so the rejected record stays in history.
    suffix = "" if existing is None else "-" + new_id()[:8]
    prior = next((s for s in current_sources(repo) if s.source_id == src["source_id"]), None)
    flag = _screen(src["content"]) if screen else None
    with repo.transaction():
        sv = repo.put_source_version(SourceVersion(
            **{**src, "id": src["id"] + suffix}, content_hash=content_hash(src["content"]), published_at=now(),
            review_status=ReviewStatus.pending, supersedes=prior.id if prior else None))
        for c in spec["claims"]:
            repo.put_claim(Claim(**{**c, "id": c["id"] + suffix}, source_version_id=sv.id,
                                 review_status=ReviewStatus.pending, reviewed_at=None))
        if flag is not None:
            repo.set_meta(f"injection:{sv.id}", str(flag))
        else:
            repo._db.execute("DELETE FROM meta WHERE key=?", (f"injection:{sv.id}",))
    upd = pending_update(repo)
    for ev_id in upd.affected_evaluation_ids:
        repo.append_event(Event(evaluation_id=ev_id, type=EventType.source_change_detected,
                                payload={"source_version_id": sv.id, "product_id": sv.product_id,
                                         "diff": upd.diff, "injection_flag": flag,
                                         "injection_flagged": flag is not None and flag >= INJECTION_FLAG_THRESHOLD}))
    return upd


def pending_update(repo) -> Optional[PendingUpdate]:
    pend = [s for s in repo.list_source_versions() if s.review_status == ReviewStatus.pending]
    if not pend:
        return None
    sv = pend[-1]
    claims = repo.list_claims(sv.id)
    before = repo.list_claims(sv.supersedes) if sv.supersedes else []
    flag = repo.get_meta(f"injection:{sv.id}")
    return PendingUpdate(source_version=sv, claims=claims, diff=diff_claims(before, claims),
                         affected_evaluation_ids=_evaluations_with_comparison(repo),
                         injection_flag=float(flag) if flag is not None else None)


def review(repo, version_id: str, decision: ReviewStatus) -> SourceVersion:
    """approve → becomes current, recompute current evaluations (comparison_updated);
    reject → pending cleared, prior approved version kept. Emits source_reviewed."""
    if decision not in (ReviewStatus.approved, ReviewStatus.rejected):
        raise ConflictError("decision must be approved or rejected")
    sv = repo.get_source_version(version_id)
    if sv.review_status != ReviewStatus.pending:
        raise ConflictError(f"source version is already {sv.review_status.value}")
    affected = _evaluations_with_comparison(repo)
    ts = now()
    with repo.transaction():
        sv.review_status = decision
        repo.set_source_review(sv.id, sv)
        for c in repo.list_claims(sv.id):
            c.review_status = decision
            c.reviewed_at = ts
            repo.put_claim(c)
    for ev_id in affected:
        repo.append_event(Event(evaluation_id=ev_id, type=EventType.source_reviewed,
                                payload={"source_version_id": sv.id, "decision": decision.value,
                                         "product_id": sv.product_id}))
    if decision == ReviewStatus.approved:
        from sv.proofpath import evaluation
        for ev_id in affected:
            try:
                evaluation.recompute(repo, ev_id, emit=True)
            except Exception:
                log.exception("recompute after review failed for %s", ev_id)
    return sv
