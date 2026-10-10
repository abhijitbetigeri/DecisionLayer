"""Generate example payloads from the frozen contracts (so they always validate).

  uv run python -m sv.proofpath.examples.build

Scenario: preset eu_technical, after the FlowBridge POC passed, before the RelayWorks v2 update.
Values follow proofpath/plan/shared-truth.md. These are UI fixtures, not the WS1 seed data.
"""
from __future__ import annotations

import json
from pathlib import Path

from sv.proofpath.contracts import (AgentResult, Artifact, BriefVersion, Claim, ComparisonSnapshot,
                                    Evaluation, EvidenceStatus, Finding, FindingStatus, FitDecision,
                                    PendingUpdate, POCRun, ProductComparison, ReportVersion,
                                    Requirement, ReviewStatus, RunOutcome, RunState, SourceVersion,
                                    TestResult, TestStatus, Workspace, now)

OUT = Path(__file__).parent
EV = "11111111-1111-4111-8111-111111111111"


def req(key, label, hard, weight=0.0, expected=None, criteria=""):
    return Requirement(id=f"req-{key}", key=key, label=label, hard=hard, weight=weight,
                       expected=expected, acceptance_criteria=criteria)


REQS = [
    req("eu_hosting", "EU deployment", True, criteria="Documented EU deployment option on a purchasable plan"),
    req("sso", "Single sign-on (SAML)", True, criteria="Documented SAML SSO on a purchasable plan"),
    req("recovery_demonstrated", "Failed syncs recover without duplicates (demonstrated)", True,
        criteria="Passing crm_warehouse_sync/v1 run linked to this brief version"),
    req("idempotent_delivery", "No duplicate records on retry (documented)", False, weight=1.0),
]

brief = BriefVersion(id="brief-v1", evaluation_id=EV, version=1,
                     goal="Sync Salesforce opportunities into Snowflake with EU hosting, SSO and duplicate-free recovery",
                     systems=["Salesforce (CRM)", "Snowflake (warehouse)"], requirements=REQS,
                     confirmed_at=now(), parsed_by="openrouter/google/gemma-4-31b-it", input_hash="sha256:demo")
evaluation = Evaluation(id=EV, session_id="session-demo", preset_id="eu_technical",
                        brief_text="We need to sync Salesforce opportunities into Snowflake, require EU hosting and SSO, "
                                   "and need failed syncs to recover without duplicate records.",
                        current_brief_version_id=brief.id)

src_fb = SourceVersion(id="src-flowbridge-v1", source_id="flowbridge-docs", product_id="flowbridge",
                       origin="FlowBridge pricing and security pages (fixture)", content_hash="sha256:fb1",
                       content="Team $299/mo. Business $999/mo. Enterprise: contact us. EU deployment on Business and Enterprise. "
                               "US deployment on all plans. Automatic retries with idempotency keys (Business+).")
src_rw = SourceVersion(id="src-relayworks-v1", source_id="relayworks-docs", product_id="relayworks",
                       origin="RelayWorks pricing page (fixture)", content_hash="sha256:rw1",
                       content="Business $899/mo with EU deployment and SAML SSO. Retries with deduplication.")
src_ps = SourceVersion(id="src-pipestack-v1", source_id="pipestack-docs", product_id="pipestack",
                       origin="PipeStack pricing page (fixture)", content_hash="sha256:ps1",
                       content="Business $699/mo. US-hosted only. SAML SSO included.")

claims = [
    Claim(id="clm-fb-eu", source_version_id=src_fb.id, requirement_key="eu_hosting", value=["business", "enterprise"], plan="business"),
    Claim(id="clm-fb-idem", source_version_id=src_fb.id, requirement_key="idempotent_delivery", value=True, plan="business"),
    Claim(id="clm-rw-eu", source_version_id=src_rw.id, requirement_key="eu_hosting", value=["business"], plan="business"),
    Claim(id="clm-rw-sso", source_version_id=src_rw.id, requirement_key="sso", value=True, plan="business"),
    Claim(id="clm-ps-eu", source_version_id=src_ps.id, requirement_key="eu_hosting", value=False),
    Claim(id="clm-ps-sso", source_version_id=src_ps.id, requirement_key="sso", value=True, plan="business"),
]

run = POCRun(id="run-1", evaluation_id=EV, brief_version_id=brief.id, state=RunState.closed,
             outcome=RunOutcome.passed, idempotency_key="demo-key-1", payload_hash="sha256:p", attempts=3)
art = Artifact(id="art-1", run_id=run.id, name="delivery_log.json",
               content={"attempts": [{"record": "opp-001", "attempt": 1, "ok": True},
                                     {"record": "opp-002", "attempt": 1, "ok": False, "error": "transient: warehouse timeout (injected)"},
                                     {"record": "opp-002", "attempt": 2, "ok": True}],
                        "destination_count": {"opp-001": 1, "opp-002": 1}})
results = [
    TestResult(id="tr-1", run_id=run.id, test_key="insert_first", status=TestStatus.pass_,
               expected={"id": "opp-001", "amount": 48200}, observed={"id": "opp-001", "amount": 48200}, artifact_ids=[art.id]),
    TestResult(id="tr-2", run_id=run.id, test_key="transient_failure", status=TestStatus.pass_,
               expected="failure before commit, retry event", observed="TransientError on attempt 1, poc_attempt emitted", artifact_ids=[art.id]),
    TestResult(id="tr-3", run_id=run.id, test_key="bounded_retry", status=TestStatus.pass_,
               expected="success within 3 attempts, same idempotency key", observed="success on attempt 2, key reused", artifact_ids=[art.id]),
    TestResult(id="tr-4", run_id=run.id, test_key="single_record", status=TestStatus.pass_,
               expected=1, observed=1, artifact_ids=[art.id],
               limitations="Applies to the tested failure mode on local mocks, not every crash scenario"),
]


def f(rid, key, product, status, basis, claims_=(), tests=(), plan=None, reason="", lim=""):
    return Finding(requirement_id=rid, requirement_key=key, product_id=product, status=status, basis=basis,
                   claim_ids=list(claims_), test_result_ids=list(tests), applicable_plan=plan, reason=reason, limitations=lim)


fb = [f("req-eu_hosting", "eu_hosting", "flowbridge", FindingStatus.met, EvidenceStatus.documented, ["clm-fb-eu"], plan="business",
        reason="EU deployment documented on Business and Enterprise"),
      f("req-sso", "sso", "flowbridge", FindingStatus.unknown, EvidenceStatus.unknown,
        reason="No FlowBridge source states SAML SSO", lim="Needs vendor evidence before a fit can be confirmed"),
      f("req-recovery_demonstrated", "recovery_demonstrated", "flowbridge", FindingStatus.met, EvidenceStatus.demonstrated,
        tests=["tr-2", "tr-3", "tr-4"], reason="Demonstrated by run-1: injected failure, bounded retry, exactly one record",
        lim="Local mock integrations; tested failure mode only"),
      f("req-idempotent_delivery", "idempotent_delivery", "flowbridge", FindingStatus.met, EvidenceStatus.documented, ["clm-fb-idem"],
        plan="business", reason="Idempotency keys documented on Business+")]
rw = [f("req-eu_hosting", "eu_hosting", "relayworks", FindingStatus.met, EvidenceStatus.documented, ["clm-rw-eu"], plan="business", reason="EU on Business"),
      f("req-sso", "sso", "relayworks", FindingStatus.met, EvidenceStatus.documented, ["clm-rw-sso"], plan="business", reason="SAML SSO on Business"),
      f("req-recovery_demonstrated", "recovery_demonstrated", "relayworks", FindingStatus.unknown, EvidenceStatus.documented,
        reason="Recovery documented only; no independent run", lim="Demonstration required by this brief")]
ps = [f("req-eu_hosting", "eu_hosting", "pipestack", FindingStatus.unmet, EvidenceStatus.documented, ["clm-ps-eu"], reason="Documented US-only"),
      f("req-sso", "sso", "pipestack", FindingStatus.met, EvidenceStatus.documented, ["clm-ps-sso"], plan="business", reason="SAML SSO documented"),
      f("req-recovery_demonstrated", "recovery_demonstrated", "pipestack", FindingStatus.unknown, EvidenceStatus.unknown, reason="No recovery claim")]

snapshot = ComparisonSnapshot(id="cmp-1", evaluation_id=EV, brief_version_id=brief.id,
                              source_version_ids=[src_fb.id, src_rw.id, src_ps.id], run_ids=[run.id], products=[
    ProductComparison(product_id="flowbridge", product_name="FlowBridge", decision=FitDecision.needs_verification, findings=fb,
                      cheapest_qualifying_plan="business", monthly_price_usd=999, evaluated_score=1.0, coverage=1.0,
                      gaps=["SSO: no evidence"]),
    ProductComparison(product_id="relayworks", product_name="RelayWorks", decision=FitDecision.needs_verification, findings=rw,
                      cheapest_qualifying_plan="business", monthly_price_usd=899, evaluated_score=None, coverage=0.0,
                      gaps=["Recovery not demonstrated"]),
    ProductComparison(product_id="pipestack", product_name="PipeStack", decision=FitDecision.not_fit, findings=ps,
                      cheapest_qualifying_plan=None, monthly_price_usd=699, evaluated_score=None, coverage=0.0,
                      gaps=["EU deployment unavailable (documented US-only)"]),
])

src_rw2 = SourceVersion(id="src-relayworks-v2", source_id="relayworks-docs", product_id="relayworks",
                        origin="RelayWorks pricing page, updated (fixture)", content_hash="sha256:rw2",
                        content="Business $899/mo (US only). EU deployment now on Enterprise only (contact sales). SAML SSO on Business.",
                        review_status=ReviewStatus.pending, supersedes=src_rw.id)
pending = PendingUpdate(source_version=src_rw2,
                        claims=[Claim(id="clm-rw2-eu", source_version_id=src_rw2.id, requirement_key="eu_hosting",
                                      value=["enterprise"], plan="enterprise", review_status=ReviewStatus.pending)],
                        diff=[{"requirement_key": "eu_hosting", "before": "Business ($899/mo)", "after": "Enterprise only (quote)"}],
                        affected_evaluation_ids=[EV], injection_flag=0.01)

report = ReportVersion(id="rep-1", evaluation_id=EV, brief_version_id=brief.id, comparison_snapshot_id=snapshot.id,
                       run_ids=[run.id], findings=fb, decision=FitDecision.needs_verification, snapshot=snapshot, brief=brief)
agent_result = AgentResult(id="agr-1", evaluation_id=EV, mode="ai_agent", model_id="openrouter/openai/gpt-oss-120b",
                           input_version=f"{brief.id}+{snapshot.id}", decision=FitDecision.needs_verification,
                           requirement_statuses={"eu_hosting": FindingStatus.met, "sso": FindingStatus.unknown,
                                                 "recovery_demonstrated": FindingStatus.met},
                           citations=["clm-fb-eu", "tr-4"], expected_decision=FitDecision.needs_verification, correct=True, turns=3)
workspace = Workspace(evaluation=evaluation, brief=brief, sources=[src_fb, src_rw, src_ps], claims=claims,
                      comparison=snapshot, flowbridge_decision=FitDecision.needs_verification, latest_run=run,
                      latest_results=results, reports=[report.id], agent_result=agent_result)
agent_context = {
    "evaluation_id": EV, "brief": json.loads(brief.model_dump_json()),
    "products": [json.loads(p.model_dump_json()) for p in snapshot.products],
    "claims": [json.loads(c.model_dump_json()) for c in claims],
    "test_results": [json.loads(r.model_dump_json()) for r in results],
    "decision_rule": "any verified unmet hard requirement -> not_fit; else any unknown hard requirement -> needs_verification; else fit",
    "limitations": ["Fictional products and evidence; live tests use local mock integrations."],
}


def dump(obj) -> dict:
    return json.loads(obj.model_dump_json()) if hasattr(obj, "model_dump_json") else obj


def main() -> None:
    files = {
        "create_evaluation": {"evaluation_id": EV, "brief": dump(brief.model_copy(update={"confirmed_at": None}))},
        "brief": dump(brief),
        "confirm": {"brief": dump(brief), "comparison": dump(snapshot)},
        "workspace": dump(workspace),
        "run": {"run": dump(run), "results": [dump(r) for r in results],
                "artifacts": [{"id": art.id, "name": art.name, "media_type": art.media_type}]},
        "artifact": dump(art),
        "pending_update": dump(pending),
        "source_version": dump(src_rw2.model_copy(update={"review_status": ReviewStatus.approved})),
        "report": dump(report),
        "agent_context": agent_context,
        "agent_result": dump(agent_result),
    }
    for name, data in files.items():
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {len(files)} examples to {OUT}")


if __name__ == "__main__":
    main()
