"""WS4: reports are frozen copies; the report page renders only from the frozen dict."""
import json
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from sv.proofpath.contracts import (BriefVersion, Claim, ComparisonSnapshot, Evaluation,
                                    EvidenceStatus, FindingStatus, FitDecision, ReviewStatus,
                                    SourceVersion)
from sv.proofpath.reports import create_report
from sv.proofpath.repository import ConflictError, Repository, dumps

ROOT = Path(__file__).resolve().parents[2] / "sv" / "proofpath"
EXAMPLE = json.loads((ROOT / "examples" / "workspace.json").read_text())


@pytest.fixture
def seeded():
    repo = Repository(":memory:")
    ev = repo.create_evaluation(Evaluation.model_validate(EXAMPLE["evaluation"]))
    brief = repo.append_brief(BriefVersion.model_validate(EXAMPLE["brief"]))
    for s in EXAMPLE["sources"]:
        repo.put_source_version(SourceVersion.model_validate(s))
    for c in EXAMPLE["claims"]:
        repo.put_claim(Claim.model_validate(c))
    snap = repo.put_comparison(ComparisonSnapshot.model_validate(EXAMPLE["comparison"]))
    return repo, ev, brief, snap


def _apply_relayworks_v2(repo, snap):
    """Simulate the approved RelayWorks v2 update: new source, new snapshot, and (worst case) an
    in-place mutation of the old snapshot row, which a frozen report must not observe."""
    v2 = SourceVersion(id="src-relayworks-v2", source_id="relayworks-docs", product_id="relayworks",
                       origin="RelayWorks pricing page, updated (fixture)", content_hash="sha256:rw2",
                       content="EU deployment now on Enterprise only (contact sales).",
                       supersedes="src-relayworks-v1", review_status=ReviewStatus.approved)
    repo.put_source_version(v2)
    repo.put_claim(Claim(id="clm-rw2-eu", source_version_id=v2.id, requirement_key="eu_hosting",
                         value=["enterprise"], plan="enterprise", evidence_status=EvidenceStatus.documented))

    live = repo.get_comparison(snap.id)
    live.source_version_ids = [i.replace("src-relayworks-v1", v2.id) for i in live.source_version_ids]
    for p in live.products:
        if p.product_id == "relayworks":
            p.cheapest_qualifying_plan, p.monthly_price_usd = "enterprise", None
            p.gaps = ["EU now Enterprise-only (quote)"]
        if p.product_id == "flowbridge":
            p.findings[0].status = FindingStatus.unknown       # hostile mutation of a cited finding
            p.decision = FitDecision.not_fit
    repo.put_comparison(live)                                   # overwrite the same snapshot id
    new = live.model_copy(update={"id": "cmp-2"}, deep=True)
    repo.put_comparison(new)
    return v2


def test_report_references_exact_versions(seeded):
    repo, ev, brief, snap = seeded
    report = create_report(repo, ev.id, brief.id, snap.id)
    assert report.brief_version_id == brief.id
    assert report.comparison_snapshot_id == snap.id
    assert report.run_ids == snap.run_ids == ["run-1"]
    assert report.decision == FitDecision.needs_verification
    assert [f.requirement_key for f in report.findings] == \
        [f.requirement_key for f in snap.products[0].findings]
    assert repo.get_report(report.id).model_dump() == report.model_dump()


def test_report_stays_frozen_after_evidence_update(seeded):
    repo, ev, brief, snap = seeded
    report = create_report(repo, ev.id, brief.id, snap.id)
    before = repo.get_report(report.id).model_dump_json()

    _apply_relayworks_v2(repo, snap)
    assert "src-relayworks-v2" in repo.get_comparison(snap.id).source_version_ids   # live data did change

    stored = repo.get_report(report.id)
    assert stored.model_dump_json() == before
    assert "src-relayworks-v1" in stored.snapshot.source_version_ids
    assert "src-relayworks-v2" not in stored.snapshot.source_version_ids
    rw = next(p for p in stored.snapshot.products if p.product_id == "relayworks")
    assert rw.monthly_price_usd == 899.0 and rw.cheapest_qualifying_plan == "business"
    assert stored.findings[0].status == FindingStatus.met
    assert stored.decision == FitDecision.needs_verification


def test_report_html_renders_only_frozen_v1_evidence(seeded):
    repo, ev, brief, snap = seeded
    report = create_report(repo, ev.id, brief.id, snap.id)
    _apply_relayworks_v2(repo, snap)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    html = env.get_template("report.html").render(report=dumps(repo.get_report(report.id)), demo_mode="local")
    assert "src-relayworks-v1" in html and "src-relayworks-v2" not in html
    assert "$899/mo" in html and "EU now Enterprise-only" not in html
    assert "Needs verification" in html
    assert "Fictional products and evidence; live tests use local mock integrations." in html
    assert "Demo sandbox: mock CRM and warehouse stand-ins" in html
    assert "ProofPath" not in html and "—" not in html and "–" not in html
    for label in ("Met", "Unknown", "Documented", "Demonstrated"):
        assert label in html


def test_new_report_after_update_captures_new_snapshot(seeded):
    repo, ev, brief, snap = seeded
    old = create_report(repo, ev.id, brief.id, snap.id)
    _apply_relayworks_v2(repo, snap)
    new = create_report(repo, ev.id, brief.id, "cmp-2")
    assert new.id != old.id
    assert "src-relayworks-v2" in new.snapshot.source_version_ids
    assert "src-relayworks-v2" not in repo.get_report(old.id).snapshot.source_version_ids


def test_report_rejects_mismatched_brief(seeded):
    repo, ev, brief, snap = seeded
    other = repo.append_brief(BriefVersion.model_validate({**EXAMPLE["brief"], "id": "brief-v2"}))
    with pytest.raises(ConflictError):
        create_report(repo, ev.id, other.id, snap.id)


def test_persona_switch_is_presentation_only():
    """The persona switch only toggles a data attribute and CSS emphasis; it never re-fetches or
    re-renders facts, statuses, weights or results (README: switching never changes truth)."""
    js = (ROOT / "static" / "workspace.js").read_text()
    start = js.index("function setPersona")
    body = js[start:js.index("\n  }\n", start)]
    assert "dataset.persona" in body
    for forbidden in ("fetch(", "api(", "render", "innerHTML", "status", "weight"):
        assert forbidden not in body, forbidden
