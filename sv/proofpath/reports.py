"""Immutable report snapshots (WS4).

A report is a frozen copy of one confirmed brief version and one comparison snapshot, plus the
run ids that snapshot used. The report page renders only from this frozen copy, so later evidence
updates (for example RelayWorks v2) never change an existing report.
"""
from __future__ import annotations

from sv.proofpath.contracts import FitDecision, ReportVersion
from sv.proofpath.repository import ConflictError, Repository

PRIMARY_PRODUCT = "flowbridge"


def create_report(repo: Repository, evaluation_id: str, brief_version_id: str,
                  comparison_snapshot_id: str) -> ReportVersion:
    """Freeze a full copy of the brief and comparison snapshot as a new ReportVersion."""
    repo.get_evaluation(evaluation_id)                          # NotFoundError -> 404
    brief = repo.get_brief(brief_version_id)
    snapshot = repo.get_comparison(comparison_snapshot_id)
    if brief.evaluation_id != evaluation_id or snapshot.evaluation_id != evaluation_id:
        raise ConflictError("brief or comparison belongs to a different evaluation")
    if snapshot.brief_version_id != brief.id:
        raise ConflictError("comparison snapshot was computed for a different brief version")

    # Deep copies via a JSON round trip: nothing in the report shares state with live objects.
    frozen_brief = type(brief).model_validate_json(brief.model_dump_json())
    frozen_snapshot = type(snapshot).model_validate_json(snapshot.model_dump_json())

    primary = next((p for p in frozen_snapshot.products if p.product_id == PRIMARY_PRODUCT), None)
    findings = [f.model_copy(deep=True) for f in primary.findings] if primary else []
    decision = primary.decision if primary else FitDecision.needs_verification

    report = ReportVersion(
        evaluation_id=evaluation_id,
        brief_version_id=frozen_brief.id,
        comparison_snapshot_id=frozen_snapshot.id,
        run_ids=list(frozen_snapshot.run_ids),
        findings=findings,
        decision=decision,
        snapshot=frozen_snapshot,
        brief=frozen_brief,
    )
    return repo.create_report(report)
