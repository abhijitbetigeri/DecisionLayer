"""Deterministic findings, the fit decision rule and the workspace projection (WS1).

No model touches anything in this module. Decision rule (README / shared-truth §4): any verified
`unmet` hard requirement → not_fit; else any `unknown` (incl. contradicted) hard requirement →
needs_verification; else fit. Preferences never override hard constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sv.proofpath import comparison, evidence, fixtures
from sv.proofpath.contracts import (SCENARIO_VERSION, BriefVersion, Claim, ComparisonSnapshot,
                                    EvidenceStatus, Evaluation, Event, EventType, Finding,
                                    FindingStatus, FitDecision, POCRun, ProductComparison,
                                    ReviewStatus, RunOutcome, SourceVersion, TestResult, TestStatus,
                                    Workspace)

POC_PRODUCT = "flowbridge"            # the crm_warehouse_sync/v1 sandbox runs FlowBridge
CAPABILITY_KEYS = ("eu_hosting", "us_hosting", "sso", "idempotent_delivery")
POC_LIMITATIONS = "Local mock integrations (Salesforce and Snowflake stand-ins); tested failure mode only"


def _plan_label(p: Optional[str]) -> str:
    return fixtures.PLAN_LABELS.get(p, p or "")


def _plans_text(plans: list[str]) -> str:
    return ", ".join(_plan_label(p) for p in plans)


# ------------------------------------------------------------------ inputs
@dataclass
class ProductEvidence:
    product_id: str
    source: SourceVersion
    claims: list[Claim]
    plans: list[str]

    def claim(self, key: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.requirement_key == key), None)

    def price_claim(self, plan: Optional[str]) -> Optional[Claim]:
        return next((c for c in self.claims if c.requirement_key == "budget_monthly_usd" and c.plan == plan), None)


@dataclass
class RunEvidence:
    """POC runs linked to the brief version (only terminal runs count)."""
    considered: list[POCRun] = field(default_factory=list)
    passing: Optional[tuple[POCRun, list[TestResult]]] = None
    failing: Optional[tuple[POCRun, list[TestResult]]] = None


def load_evidence(repo) -> dict[str, ProductEvidence]:
    sources = evidence.current_sources(repo)
    out: dict[str, ProductEvidence] = {}
    for s in sources:
        claims = evidence.current_claims(repo, [s])
        out[s.product_id] = ProductEvidence(s.product_id, s, claims, evidence.plans_for(s, claims))
    return out


def load_runs(repo, brief: BriefVersion) -> RunEvidence:
    runs = [r for r in repo.list_runs(brief.evaluation_id)
            if r.brief_version_id == brief.id and r.scenario_version == SCENARIO_VERSION and r.outcome is not None]
    ev = RunEvidence(considered=runs)
    for r in runs:                                   # oldest → newest; latest wins
        results = repo.list_results(r.id)
        if r.outcome == RunOutcome.passed and results and all(t.status == TestStatus.pass_ for t in results):
            ev.passing = (r, results)
        elif r.outcome == RunOutcome.failed:
            ev.failing = (r, results)
    return ev


# ------------------------------------------------------------------ findings
def _restrictions(brief: BriefVersion, pe: ProductEvidence) -> dict[str, list[str]]:
    """Plans allowed by each documented hard capability (no claim → no restriction)."""
    out: dict[str, list[str]] = {}
    for r in brief.requirements:
        if not r.hard:
            continue
        key = "idempotent_delivery" if r.key == "recovery_demonstrated" else r.key
        if key not in CAPABILITY_KEYS:
            continue
        c = pe.claim(key)
        if c is None:
            continue
        out[r.key] = list(c.value) if isinstance(c.value, list) else []
    return out


def qualifying_plan(brief: BriefVersion, pe: ProductEvidence) -> tuple[Optional[str], Optional[float]]:
    restr = _restrictions(brief, pe)
    for plan in pe.plans:                            # cheapest first, quote-only last
        if all(plan in allowed for allowed in restr.values()):
            pc = pe.price_claim(plan)
            return plan, (float(pc.value) if pc and pc.value is not None else None)
    return None, None


def _capability(req, pe: ProductEvidence, name: str, plan: Optional[str]) -> Finding:
    base = dict(requirement_id=req.id, requirement_key=req.key, product_id=pe.product_id)
    c = pe.claim(req.key)
    if c is None:
        return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.unknown,
                       reason=f"No current {name} source states {req.label}; not confirmed",
                       limitations="Needs vendor evidence before a fit can be confirmed")
    if isinstance(c.value, list) and c.value:
        applicable = plan if plan in c.value else c.value[0]
        return Finding(**base, status=FindingStatus.met, basis=c.evidence_status, claim_ids=[c.id],
                       applicable_plan=applicable,
                       reason=f"{req.label} documented on {_plans_text(c.value)} ({pe.source.origin})")
    return Finding(**base, status=FindingStatus.unmet, basis=c.evidence_status, claim_ids=[c.id],
                   reason=f"{pe.source.origin} documents that {req.label} is not available")


def _recovery(req, pe: ProductEvidence, name: str, runs: RunEvidence) -> Finding:
    base = dict(requirement_id=req.id, requirement_key=req.key, product_id=pe.product_id)
    doc = pe.claim("idempotent_delivery")
    doc_ids = [doc.id] if doc and isinstance(doc.value, list) and doc.value else []
    if pe.product_id == POC_PRODUCT and runs.passing:
        run, results = runs.passing
        return Finding(**base, status=FindingStatus.met, basis=EvidenceStatus.demonstrated,
                       claim_ids=doc_ids, test_result_ids=[t.id for t in results],
                       reason=(f"Demonstrated by POC run {run.id[:8]} ({SCENARIO_VERSION}): injected failure, "
                               "bounded retry, exactly one destination record"),
                       limitations=POC_LIMITATIONS)
    if pe.product_id == POC_PRODUCT and runs.failing:
        run, results = runs.failing
        return Finding(**base, status=FindingStatus.unknown,
                       basis=EvidenceStatus.contradicted if doc_ids else EvidenceStatus.unknown,
                       claim_ids=doc_ids, test_result_ids=[t.id for t in results if t.status != TestStatus.pass_],
                       reason=f"POC run {run.id[:8]} did not pass; recovery is not demonstrated",
                       limitations="Review the failed assertions; re-run before deciding")
    if doc_ids:
        return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.documented, claim_ids=doc_ids,
                       reason=f"{name} documents retries without duplicates, but no passing "
                              f"{SCENARIO_VERSION} run demonstrates it",
                       limitations="This brief requires a demonstration; documentation alone is not enough")
    return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.unknown,
                   reason=f"No {name} source describes recovery and no run demonstrates it",
                   limitations="Needs a demonstration before a fit can be confirmed")


def _idempotent(req, pe: ProductEvidence, name: str, plan, runs: RunEvidence) -> Finding:
    f = _capability(req, pe, name, plan)
    if f.status == FindingStatus.unknown and pe.product_id == POC_PRODUCT and runs.passing:
        run, results = runs.passing
        return Finding(requirement_id=req.id, requirement_key=req.key, product_id=pe.product_id,
                       status=FindingStatus.met, basis=EvidenceStatus.demonstrated,
                       test_result_ids=[t.id for t in results],
                       reason=f"Single destination record after retry, demonstrated by POC run {run.id[:8]}",
                       limitations=POC_LIMITATIONS)
    return f


def _budget(req, pe: ProductEvidence, plan: Optional[str], price: Optional[float]) -> Finding:
    base = dict(requirement_id=req.id, requirement_key=req.key, product_id=pe.product_id)
    try:
        ceiling = float(req.expected)
    except (TypeError, ValueError):
        return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.unknown,
                       reason="No budget ceiling set", limitations="Add a monthly ceiling to evaluate cost")
    if plan is None:
        return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.unknown,
                       reason="No plan meets the documented capability requirements, so no price applies")
    pc = pe.price_claim(plan)
    ids = [pc.id] if pc else []
    if price is None:
        return Finding(**base, status=FindingStatus.unknown, basis=EvidenceStatus.documented, claim_ids=ids,
                       applicable_plan=plan,
                       reason=f"Cheapest qualifying plan is {_plan_label(plan)}, which is quote-only; "
                              "price unknown until a quote is obtained",
                       limitations="Not a confirmed budget fit")
    if price <= ceiling:
        return Finding(**base, status=FindingStatus.met, basis=EvidenceStatus.documented, claim_ids=ids,
                       applicable_plan=plan,
                       reason=f"{_plan_label(plan)} at ${price:g}/month is within the ${ceiling:g} ceiling",
                       limitations="List price; seats, usage, term, implementation and support not included")
    return Finding(**base, status=FindingStatus.unmet, basis=EvidenceStatus.documented, claim_ids=ids,
                   applicable_plan=plan,
                   reason=f"Cheapest qualifying plan is {_plan_label(plan)} at ${price:g}/month, "
                          f"above the ${ceiling:g} ceiling")


def findings(brief: BriefVersion, pe: ProductEvidence, runs: RunEvidence) -> list[Finding]:
    """Deterministic findings for one product. Documented support never satisfies
    recovery_demonstrated; only a passing crm_warehouse_sync/v1 run linked to this brief can."""
    name = fixtures.PRODUCTS[pe.product_id]["name"]
    plan, price = qualifying_plan(brief, pe)
    out = []
    for r in brief.requirements:
        if r.key == "recovery_demonstrated":
            out.append(_recovery(r, pe, name, runs))
        elif r.key == "idempotent_delivery":
            out.append(_idempotent(r, pe, name, plan, runs))
        elif r.key == "budget_monthly_usd":
            out.append(_budget(r, pe, plan, price))
        else:
            out.append(_capability(r, pe, name, plan))
    return out


def decide(found: list[Finding], hard_ids: Optional[set[str]] = None) -> FitDecision:
    hard = [f for f in found if hard_ids is None or f.requirement_id in hard_ids]
    if any(f.status == FindingStatus.unmet for f in hard):
        return FitDecision.not_fit
    if any(f.status == FindingStatus.unknown or f.basis == EvidenceStatus.contradicted for f in hard):
        return FitDecision.needs_verification
    return FitDecision.fit


# ------------------------------------------------------------------ comparison snapshot
def _rubric_weights(repo, brief: BriefVersion) -> dict[str, float]:
    from sv.proofpath.requirements import preset_for_brief
    ev = repo.get_evaluation(brief.evaluation_id)
    return dict(fixtures.PRESETS[preset_for_brief(brief, ev.preset_id)]["rubric_weights"])


def product_comparison(brief: BriefVersion, pe: ProductEvidence, runs: RunEvidence,
                       rubric_weights: dict[str, float]) -> ProductComparison:
    found = findings(brief, pe, runs)
    hard_ids = {r.id for r in brief.requirements if r.hard}
    decision = decide(found, hard_ids)
    plan, price = qualifying_plan(brief, pe)
    ctx = comparison.ScoringContext(pe.product_id, tuple(fixtures.CONNECTORS.get(pe.product_id, ())),
                                    pe.product_id == POC_PRODUCT and runs.passing is not None, plan, price)
    score, coverage, notes = comparison.score_preferences(brief, found, rubric_weights, ctx)
    labels = {r.id: r.label for r in brief.requirements}
    gaps = [f"{labels[f.requirement_id]}: {f.reason}" for f in found
            if f.requirement_id in hard_ids and f.status != FindingStatus.met]
    if plan is not None and price is None:
        gaps.append(f"Cost: requirements need {_plan_label(plan)}, which is quote-only; price unknown until obtained")
    gaps += notes
    return ProductComparison(product_id=pe.product_id, product_name=fixtures.PRODUCTS[pe.product_id]["name"],
                             decision=decision, findings=found, cheapest_qualifying_plan=plan,
                             monthly_price_usd=price, evaluated_score=score, coverage=coverage, gaps=gaps)


def build_snapshot(repo, evaluation_id: str) -> ComparisonSnapshot:
    ev = repo.get_evaluation(evaluation_id)
    brief = repo.get_brief(ev.current_brief_version_id)
    ev_by_product = load_evidence(repo)
    runs = load_runs(repo, brief)
    weights = _rubric_weights(repo, brief)
    products = [product_comparison(brief, ev_by_product[p], runs, weights)
                for p in fixtures.PRODUCTS if p in ev_by_product]
    return ComparisonSnapshot(evaluation_id=evaluation_id, brief_version_id=brief.id,
                              source_version_ids=[ev_by_product[p].source.id for p in fixtures.PRODUCTS
                                                  if p in ev_by_product],
                              run_ids=[r.id for r in runs.considered], rubric_version=comparison.RUBRIC_VERSION,
                              products=products)


def recompute(repo, evaluation_id: str, emit: bool = False) -> ComparisonSnapshot:
    """Stores a NEW immutable snapshot (older snapshots and reports are untouched)."""
    snap = repo.put_comparison(build_snapshot(repo, evaluation_id))
    if emit:
        repo.append_event(Event(evaluation_id=evaluation_id, type=EventType.comparison_updated,
                                payload={"comparison_snapshot_id": snap.id,
                                         "decisions": {p.product_id: p.decision.value for p in snap.products}}))
    return snap


def _snapshot_outdated(repo, snap: ComparisonSnapshot, brief: BriefVersion) -> bool:
    if snap.brief_version_id != brief.id:
        return False                                  # stale brief: wait for confirm, keep old projection
    current_sources = [s.id for s in evidence.current_sources(repo)]
    current_runs = [r.id for r in load_runs(repo, brief).considered]
    return sorted(current_sources) != sorted(snap.source_version_ids) or current_runs != snap.run_ids


def workspace(repo, evaluation_id: str) -> Workspace:
    ev: Evaluation = repo.get_evaluation(evaluation_id)
    brief = repo.get_brief(ev.current_brief_version_id)
    # A finished POC or an approved update makes the projection outdated: rebuild it once
    # (inside a transaction so concurrent polls do not each append a snapshot).
    with repo.transaction():
        snap = repo.latest_comparison(evaluation_id)
        if snap is not None and brief.confirmed_at is not None and _snapshot_outdated(repo, snap, brief):
            snap = recompute(repo, evaluation_id, emit=True)
    pending = evidence.pending_update(repo)
    if pending is not None and evaluation_id not in pending.affected_evaluation_ids:
        pending = None
    brief_stale = brief.confirmed_at is None or (snap is not None and snap.brief_version_id != brief.id)
    current = evidence.current_sources(repo)
    current_ids = {s.id for s in current}
    history = [s for s in repo.list_source_versions()
               if s.review_status == ReviewStatus.approved and s.id not in current_ids]
    fb = None
    if snap is not None and not brief_stale:
        fb = next((p.decision for p in snap.products if p.product_id == POC_PRODUCT), None)
    runs = repo.list_runs(evaluation_id)
    latest = runs[-1] if runs else None
    return Workspace(
        evaluation=ev, brief=brief, stale=brief_stale or pending is not None, pending_update=pending,
        sources=current + history, claims=evidence.current_claims(repo, current), comparison=snap,
        flowbridge_decision=fb, latest_run=latest,
        latest_results=repo.list_results(latest.id) if latest else [],
        reports=[r.id for r in reversed(repo.list_reports(evaluation_id))],
        agent_result=repo.latest_agent_result(evaluation_id))


# ------------------------------------------------------------------ pure helper for the decision matrix
def decision_for(preset_id: str, product_id: str, *, poc_passed: bool, relayworks_v2: bool) -> FitDecision:
    """Runs the real fixtures and the real rule end to end on an in-memory repository."""
    from sv.proofpath.repository import Repository
    from sv.proofpath.requirements import preset_brief

    repo = Repository(":memory:")
    evidence.seed(repo)
    ev = repo.create_evaluation(Evaluation(session_id="decision-matrix", preset_id=preset_id,
                                           brief_text=fixtures.PRESETS[preset_id]["brief_text"]))
    brief = repo.append_brief(preset_brief(preset_id, ev.id))
    repo.confirm_brief(brief.id)
    recompute(repo, ev.id)
    if poc_passed:
        add_passing_run(repo, ev.id, brief.id)
    if relayworks_v2:
        upd = evidence.simulate_update(repo, "relayworks_v2", screen=False)
        evidence.review(repo, upd.source_version.id, ReviewStatus.approved)
    snap = recompute(repo, ev.id)
    return next(p.decision for p in snap.products if p.product_id == product_id)


def add_passing_run(repo, evaluation_id: str, brief_version_id: str) -> POCRun:
    """Test helper: a completed, passing crm_warehouse_sync/v1 run with its four assertions."""
    from sv.proofpath.contracts import RunState
    run = repo.create_run(POCRun(evaluation_id=evaluation_id, brief_version_id=brief_version_id,
                                 idempotency_key=f"test-{evaluation_id[:8]}", state=RunState.closed,
                                 outcome=RunOutcome.passed, attempts=2))
    for key in ("insert_first", "transient_failure", "bounded_retry", "single_record"):
        repo.put_result(TestResult(run_id=run.id, test_key=key, status=TestStatus.pass_, expected=True, observed=True))
    return run
