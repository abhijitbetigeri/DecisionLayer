"""Frozen domain contracts for the Evaluation Workspace (schema version 1).

Every workstream imports these types; nobody defines payloads independently. Changes go through
the coordinator, who updates this file, sv/proofpath/examples/*.json and all consumers together.
See proofpath/README.md "Contract freeze" and proofpath/plan/shared-truth.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- enums
class FindingStatus(str, Enum):
    met = "met"
    unmet = "unmet"
    unknown = "unknown"


class EvidenceStatus(str, Enum):
    documented = "documented"
    demonstrated = "demonstrated"
    unknown = "unknown"
    contradicted = "contradicted"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TestStatus(str, Enum):
    __test__ = False  # keep pytest from collecting this enum
    pass_ = "pass"
    fail = "fail"
    blocked = "blocked"


class FitDecision(str, Enum):
    fit = "fit"
    not_fit = "not_fit"
    needs_verification = "needs_verification"


class RunState(str, Enum):
    draft = "draft"
    awaiting_approval = "awaiting_approval"
    queued = "queued"
    provisioning = "provisioning"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    cleaning_up = "cleaning_up"
    closed = "closed"


class RunOutcome(str, Enum):
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    interrupted = "interrupted"


class Persona(str, Enum):
    technical = "technical"
    finance = "finance"


class EventType(str, Enum):
    brief_parsed = "brief_parsed"
    brief_confirmed = "brief_confirmed"
    workspace_generated = "workspace_generated"
    poc_queued = "poc_queued"
    poc_started = "poc_started"
    poc_attempt = "poc_attempt"
    poc_test_result = "poc_test_result"
    poc_finished = "poc_finished"
    poc_cleanup_finished = "poc_cleanup_finished"
    source_change_detected = "source_change_detected"
    source_reviewed = "source_reviewed"
    comparison_updated = "comparison_updated"
    report_created = "report_created"
    agent_evaluation_finished = "agent_evaluation_finished"


REQUIREMENT_KEYS = ("eu_hosting", "us_hosting", "sso", "recovery_demonstrated",
                    "idempotent_delivery", "budget_monthly_usd")
PRODUCT_IDS = ("flowbridge", "relayworks", "pipestack")
PRESET_IDS = ("eu_technical", "us_operations", "strict_budget")
SCENARIO_VERSION = "crm_warehouse_sync/v1"


# ---------------------------------------------------------------- domain types
class Model(BaseModel):
    model_config = {"use_enum_values": False}


class Requirement(Model):
    id: str = Field(default_factory=new_id)
    key: str                                  # one of REQUIREMENT_KEYS
    label: str
    hard: bool
    weight: float = 0.0                       # preference weight; ignored for hard requirements
    expected: Optional[Any] = None            # e.g. 900 for budget_monthly_usd
    acceptance_criteria: str = ""


class BriefVersion(Model):
    id: str = Field(default_factory=new_id)
    evaluation_id: str
    version: int
    goal: str
    systems: list[str]
    persona: Persona = Persona.technical
    requirements: list[Requirement]
    confirmed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)
    # provenance (README: record model identity and input version for model calls)
    parsed_by: str = "preset"                 # model id, "preset" or "manual"
    input_hash: Optional[str] = None
    dropped_terms: list[str] = []             # model-proposed keys outside the allowlist


class Evaluation(Model):
    id: str = Field(default_factory=new_id)
    session_id: str
    preset_id: Optional[str] = None
    brief_text: str
    current_brief_version_id: Optional[str] = None
    created_at: datetime = Field(default_factory=now)


class SourceVersion(Model):
    id: str = Field(default_factory=new_id)
    source_id: str                            # stable id of the source document
    product_id: str
    origin: str                               # human label, e.g. "RelayWorks pricing page (fixture)"
    content_hash: str
    retrieved_at: datetime = Field(default_factory=now)
    published_at: Optional[datetime] = None
    content: str
    fictional: bool = True
    review_status: ReviewStatus = ReviewStatus.approved
    supersedes: Optional[str] = None          # previous approved version id


class Claim(Model):
    id: str = Field(default_factory=new_id)
    source_version_id: str
    requirement_key: str
    value: Any                                # True/False, plan list, price, region list...
    plan: Optional[str] = None                # plan the claim applies to
    evidence_status: EvidenceStatus = EvidenceStatus.documented
    review_status: ReviewStatus = ReviewStatus.approved
    reviewed_at: Optional[datetime] = None


class Finding(Model):
    requirement_id: str
    requirement_key: str
    product_id: str
    status: FindingStatus
    basis: EvidenceStatus
    claim_ids: list[str] = []
    test_result_ids: list[str] = []
    applicable_plan: Optional[str] = None
    reason: str
    limitations: str = ""


class POCRun(Model):
    id: str = Field(default_factory=new_id)
    evaluation_id: str
    brief_version_id: str
    scenario_version: str = SCENARIO_VERSION
    state: RunState = RunState.queued
    outcome: Optional[RunOutcome] = None
    idempotency_key: str
    payload_hash: str = ""
    attempts: int = 0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    expires_at: Optional[datetime] = None


class TestResult(Model):
    __test__ = False
    id: str = Field(default_factory=new_id)
    run_id: str
    test_key: str                              # insert_first | transient_failure | bounded_retry | single_record
    status: TestStatus
    expected: Any
    observed: Any
    artifact_ids: list[str] = []
    limitations: str = ""


class Artifact(Model):
    id: str = Field(default_factory=new_id)
    run_id: str
    name: str
    media_type: str = "application/json"
    content: Any                               # small JSON only; bounded by the POC runner


class ProductComparison(Model):
    product_id: str
    product_name: str
    decision: FitDecision
    findings: list[Finding]
    cheapest_qualifying_plan: Optional[str] = None
    monthly_price_usd: Optional[float] = None  # None = quote / unknown
    evaluated_score: Optional[float] = None
    coverage: Optional[float] = None
    gaps: list[str] = []


class ComparisonSnapshot(Model):
    id: str = Field(default_factory=new_id)
    evaluation_id: str
    brief_version_id: str
    source_version_ids: list[str]
    run_ids: list[str]
    rubric_version: str = "rubric/v1"
    products: list[ProductComparison]
    created_at: datetime = Field(default_factory=now)


class ReportVersion(Model):
    id: str = Field(default_factory=new_id)
    evaluation_id: str
    brief_version_id: str
    comparison_snapshot_id: str
    run_ids: list[str]
    findings: list[Finding]                    # FlowBridge findings at report time
    decision: FitDecision
    snapshot: ComparisonSnapshot               # frozen copy; the report never re-reads live data
    brief: BriefVersion
    created_at: datetime = Field(default_factory=now)


class Event(Model):
    id: str = Field(default_factory=new_id)
    sequence: int = 0                          # assigned by the repository
    evaluation_id: Optional[str] = None
    run_id: Optional[str] = None
    type: EventType
    payload: dict = {}
    channel: str = "live"                      # live | simulated | replay (never mixed in metrics)
    created_at: datetime = Field(default_factory=now)


class PendingUpdate(Model):
    source_version: SourceVersion
    claims: list[Claim]
    diff: list[dict]                           # [{requirement_key, before, after}]
    affected_evaluation_ids: list[str] = []
    injection_flag: Optional[float] = None     # Jev probability that content contains AI instructions


class AgentResult(Model):
    id: str = Field(default_factory=new_id)
    evaluation_id: str
    mode: str                                  # "ai_agent" | "rule_based"
    model_id: Optional[str] = None
    input_version: str                         # brief version id + comparison snapshot id
    decision: FitDecision
    requirement_statuses: dict[str, FindingStatus]
    citations: list[str]                       # claim ids / test result ids, all validated to exist
    rejected_citations: list[str] = []
    expected_decision: Optional[FitDecision] = None
    correct: Optional[bool] = None
    turns: int = 0
    created_at: datetime = Field(default_factory=now)


class Workspace(Model):
    """What GET /evaluations/{id}/workspace returns: the whole page model."""
    evaluation: Evaluation
    brief: BriefVersion
    stale: bool = False                        # brief edited since last confirm, or pending evidence review
    pending_update: Optional[PendingUpdate] = None
    sources: list[SourceVersion]
    claims: list[Claim]
    comparison: Optional[ComparisonSnapshot] = None
    flowbridge_decision: Optional[FitDecision] = None
    latest_run: Optional[POCRun] = None
    latest_results: list[TestResult] = []
    reports: list[str] = []                    # report ids, newest first
    agent_result: Optional[AgentResult] = None
    fictional_label: str = "Fictional products and evidence; live tests use local mock integrations."


# ---------------------------------------------------------------- envelopes
T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}


class Envelope(BaseModel, Generic[T]):
    schema_version: int = SCHEMA_VERSION
    data: T


class ErrorEnvelope(BaseModel):
    schema_version: int = SCHEMA_VERSION
    error: ErrorBody
