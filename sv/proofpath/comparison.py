"""Preference scoring for the comparison (WS1). Hard constraints are decided first in evaluation.py;
this module only scores preferences, with the README formulas and zero guards:

    evaluated_score = sum(weight × rubric_score) / sum(weights of evaluated criteria)
    coverage        = sum(weights of evaluated criteria) / sum(all preference weights)

A zero denominator yields `None` (and the gap "Not enough evaluated evidence"), never 0 or 1.
Rubrics are defined here, before any product is scored, and versioned by RUBRIC_VERSION.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sv.proofpath.contracts import BriefVersion, Finding, FindingStatus

RUBRIC_VERSION = "rubric/v1"
NOT_ENOUGH = "Not enough evaluated evidence"


@dataclass(frozen=True)
class ScoringContext:
    product_id: str
    connectors: tuple[str, ...]          # documented connectors (fixture source text)
    poc_passed: bool                     # passing crm_warehouse_sync/v1 run linked to this brief
    plan: Optional[str]                  # cheapest qualifying plan
    price: Optional[float]               # its monthly price; None = quote only / no plan


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    rubric: str                          # what 1.0 / 0.0 / unknown mean, shown to the buyer
    score: Callable[[BriefVersion, ScoringContext], Optional[float]]


def _connector_coverage(brief: BriefVersion, ctx: ScoringContext) -> Optional[float]:
    systems = [s.split()[0].strip("(),").lower() for s in brief.systems if s.strip()]
    if not systems:
        return None
    have = {c.lower() for c in ctx.connectors}
    return round(sum(1 for s in systems if s in have) / len(systems), 3)


def _implementation_effort(_: BriefVersion, ctx: ScoringContext) -> Optional[float]:
    return 1.0 if ctx.poc_passed else None


def _cost_clarity(_: BriefVersion, ctx: ScoringContext) -> Optional[float]:
    if ctx.plan is None:
        return None
    return 1.0 if ctx.price is not None else 0.0


RUBRIC: dict[str, Criterion] = {
    "connector_coverage": Criterion(
        "connector_coverage", "Connector coverage",
        "Share of the brief's systems with a documented connector (1.0 = all, 0.0 = none; "
        "unknown if the brief names no systems).", _connector_coverage),
    "implementation_effort": Criterion(
        "implementation_effort", "Implementation effort",
        "1.0 when the scenario was set up and passed in the sandbox with configuration only; "
        "unknown (not evaluated) until a POC run passes.", _implementation_effort),
    "cost_clarity": Criterion(
        "cost_clarity", "Cost clarity",
        "1.0 when the qualifying plan has a public monthly price; 0.0 when it is quote-only; "
        "unknown when no plan qualifies.", _cost_clarity),
}

_SOFT_SCORES = {FindingStatus.met: 1.0, FindingStatus.unmet: 0.0, FindingStatus.unknown: None}


def score(entries: list[tuple[str, float, Optional[float]]]) -> tuple[Optional[float], Optional[float]]:
    """entries = [(label, weight, rubric_score or None)]. Returns (evaluated_score, coverage)."""
    total = sum(w for _, w, _ in entries if w > 0)
    evaluated = [(w, s) for _, w, s in entries if w > 0 and s is not None]
    ev_weight = sum(w for w, _ in evaluated)
    coverage = round(ev_weight / total, 3) if total > 0 else None
    evaluated_score = round(sum(w * s for w, s in evaluated) / ev_weight, 3) if ev_weight > 0 else None
    return evaluated_score, coverage


def preference_entries(brief: BriefVersion, findings: list[Finding], rubric_weights: dict[str, float],
                       ctx: ScoringContext) -> list[tuple[str, float, Optional[float]]]:
    entries: list[tuple[str, float, Optional[float]]] = []
    by_req = {f.requirement_id: f for f in findings}
    for r in brief.requirements:
        if not r.hard:
            f = by_req.get(r.id)
            entries.append((r.label, float(r.weight), _SOFT_SCORES[f.status] if f else None))
    for key, w in rubric_weights.items():
        c = RUBRIC[key]
        entries.append((c.label, float(w), c.score(brief, ctx)))
    return entries


def score_preferences(brief: BriefVersion, findings: list[Finding], rubric_weights: dict[str, float],
                      ctx: ScoringContext) -> tuple[Optional[float], Optional[float], list[str]]:
    """Returns (evaluated_score, coverage, notes). Preferences never change the fit decision."""
    entries = preference_entries(brief, findings, rubric_weights, ctx)
    evaluated_score, coverage = score(entries)
    notes = []
    if evaluated_score is None:
        notes.append(NOT_ENOUGH)
    unevaluated = [label for label, w, s in entries if w > 0 and s is None]
    if unevaluated:
        notes.append("Not evaluated: " + ", ".join(unevaluated))
    return evaluated_score, coverage, notes
