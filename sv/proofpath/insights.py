"""Evidence-linked decision history and actionable gaps; never model-generated."""
from sv.proofpath import evaluation
from sv.proofpath.contracts import FindingStatus


def _value(value):
    return value.value if hasattr(value, "value") else value


def build_insights(repo, evaluation_id: str) -> dict:
    ws = evaluation.workspace(repo, evaluation_id)
    brief = ws.brief
    snapshots = repo._list("comparisons", "evaluation_id=?", (evaluation_id,))
    timeline = []
    previous = None
    for snap in snapshots:
        # A new brief establishes a new baseline; changed requirements are not capability changes.
        prior = {p.product_id: p for p in previous.products} if previous and previous.brief_version_id == snap.brief_version_id else {}
        changes = []
        for product in snap.products:
            old = prior.get(product.product_id)
            base = {"product_id": product.product_id, "product_name": product.product_name}
            for field in ("decision", "cheapest_qualifying_plan", "monthly_price_usd"):
                before = _value(getattr(old, field)) if old else None
                after = _value(getattr(product, field))
                if old is None or before != after:
                    changes.append({**base, "field": field, "requirement_key": None,
                                    "before": before, "after": after, "claim_ids": [], "test_result_ids": []})
            old_findings = {f.requirement_key: f for f in old.findings} if old else {}
            for finding in product.findings:
                before_finding = old_findings.get(finding.requirement_key)
                before = ({"status": before_finding.status.value, "basis": before_finding.basis.value,
                           "applicable_plan": before_finding.applicable_plan} if before_finding else None)
                after = {"status": finding.status.value, "basis": finding.basis.value,
                         "applicable_plan": finding.applicable_plan}
                if before != after:
                    changes.append({**base, "field": "finding", "requirement_key": finding.requirement_key,
                                    "before": before, "after": after, "reason": finding.reason,
                                    "claim_ids": finding.claim_ids, "test_result_ids": finding.test_result_ids,
                                    "prior_claim_ids": before_finding.claim_ids if before_finding else []})
        if changes:
            flowbridge = next((p for p in snap.products if p.product_id == "flowbridge"), None)
            baseline = not prior
            title = "Requirements evaluated" if baseline else ("POC evidence evaluated" if snap.run_ids != previous.run_ids else "Approved evidence evaluated")
            blockers = []
            snapshot_brief = repo.get_brief(snap.brief_version_id)
            hard = {r.id for r in snapshot_brief.requirements if r.hard}
            if flowbridge:
                blockers = [f.requirement_key for f in flowbridge.findings if f.requirement_id in hard and f.status != FindingStatus.met]
            summary = f"FlowBridge: {flowbridge.decision.value.replace('_', ' ')}" if flowbridge else "Comparison evaluated"
            if blockers:
                summary += "; unresolved: " + ", ".join(blockers)
            timeline.append({"id": snap.id, "created_at": snap.created_at.isoformat(),
                             "brief_version_id": snap.brief_version_id, "snapshot_id": snap.id,
                             "title": title, "summary": summary, "changes": changes,
                             "source_version_ids": snap.source_version_ids, "run_ids": snap.run_ids})
        previous = snap
    next_steps = []
    if brief.confirmed_at is None:
        next_steps.append({"id": "confirm-brief", "product_id": None, "requirement_key": None,
                           "title": "Confirm updated requirements", "owner": "Buyer",
                           "request_text": "Review and confirm this brief before using its findings for a decision.",
                           "reason": "The current brief is unconfirmed; prior comparisons apply to an earlier confirmed brief.",
                           "action": "confirm_brief", "claim_ids": [], "test_result_ids": [], "source_version_ids": []})
    elif ws.comparison and ws.comparison.brief_version_id == brief.id:
        hard = {r.id: r for r in brief.requirements if r.hard}
        claims = {c.id: c for c in repo.list_claims()}
        for product in ws.comparison.products:
            for finding in product.findings:
                if finding.requirement_id not in hard or finding.status == FindingStatus.met:
                    continue
                label = hard[finding.requirement_id].label
                key = finding.requirement_key
                if key == "recovery_demonstrated":
                    title, owner, action = "Run recovery verification", "Sales engineering", "run_poc" if product.product_id == "flowbridge" else "request_evidence"
                    request = f"Demonstrate bounded retry and exactly one destination record after a temporary failure for {product.product_name}. Provide test conditions and results."
                elif key == "budget_monthly_usd":
                    title, owner, action = "Obtain a qualifying-plan quote", "Vendor sales", "request_quote"
                    request = f"Provide a quote for {product.product_name} on the qualifying plan ({product.cheapest_qualifying_plan or 'to be identified'}), including seats, usage, support and implementation, against our monthly ceiling of ${hard[finding.requirement_id].expected}."
                else:
                    title, owner, action = f"Verify {label}", "Vendor security" if key in ("sso", "eu_hosting", "us_hosting") else "Vendor sales engineering", "request_evidence"
                    request = f"Provide current evidence confirming {label} for {product.product_name} on the proposed plan, including applicable deployment and contractual limitations."
                if finding.status == FindingStatus.unmet:
                    request += " Current evidence does not meet this requirement; identify a supported alternative or confirm the gap."
                source_ids = list(dict.fromkeys(claims[c].source_version_id for c in finding.claim_ids if c in claims))
                next_steps.append({"id": f"{product.product_id}-{key}", "product_id": product.product_id,
                                   "requirement_key": key, "title": title, "owner": owner, "request_text": request,
                                   "reason": finding.reason, "status": finding.status.value, "action": action,
                                   "claim_ids": finding.claim_ids, "test_result_ids": finding.test_result_ids,
                                   "source_version_ids": source_ids})
    if ws.pending_update:
        pending = ws.pending_update.source_version
        next_steps.insert(0, {"id": f"review-{pending.id}", "product_id": pending.product_id,
                             "requirement_key": None, "title": "Review pending source change", "owner": "Evidence reviewer",
                             "request_text": f"Review {pending.origin} and approve or reject its changed claims. Until approved, it must not alter the decision.",
                             "reason": "A source change is pending review; the comparison still uses approved evidence.",
                             "action": "review_source", "claim_ids": [], "test_result_ids": [], "source_version_ids": [pending.id]})
    return {"evaluation_id": evaluation_id, "brief_version_id": brief.id, "timeline": timeline,
            "next_steps": next_steps, "stale": ws.stale}
