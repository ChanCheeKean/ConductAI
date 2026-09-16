"""Provider-neutral records crossing ConductAI boundaries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(StrictModel):
    kind: Literal[
        "graph_node", "agent", "subagent", "tool", "memory", "sandbox",
        "harness", "governance", "evaluator", "runtime", "router", "data",
    ]
    name: str


class Budget(StrictModel):
    tool_calls: int = Field(ge=0)
    model_input_tokens: int = Field(ge=0)
    wall_seconds: int = Field(ge=0)
    replans: int = Field(ge=0)


class RouteDecision(StrictModel):
    route_id: str
    method: Literal["rule", "classifier", "fallback"]
    confidence: float = Field(ge=0, le=1)
    track: Literal["sales", "servicing", "mixed", "portfolio"]
    channel: Literal["phone", "chat", "secure_message"]
    language: Literal["english", "spanish", "code_switched"]
    depth: Literal["L1", "L2", "L3", "L4", "Q01"]
    path: str
    budget: Budget
    roles: tuple[str, ...]
    skills: tuple[str, ...]
    rationale: str


class Provenance(StrictModel):
    event_seqs: list[int] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class Finding(StrictModel):
    finding_id: str
    category: str
    status: Literal["substantiated", "unsubstantiated", "control_gap", "no_error", "insufficient_evidence"]
    attributable_to: Literal["colleague", "script", "system", "supervisor_material", "none"]
    severity: Literal["low", "medium", "high"]
    interaction_id: str
    evidence_spans: list[dict[str, Any]]
    structured_evidence: list[dict[str, Any]]
    policy_refs: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)


class AssessmentRecord(StrictModel):
    schema_version: int = 1
    run_id: str
    review_id: str
    interaction_ids: list[str]
    route: RouteDecision
    findings: list[Finding]
    customer_outcome: dict[str, Any]
    colleague_outcome: dict[str, Any]
    control_outcome: dict[str, Any]
    adjudication: dict[str, Any]
    waits: list[dict[str, Any]] = Field(default_factory=list)
    memory_ops: list[dict[str, Any]] = Field(default_factory=list)
    graph_writes: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    summary_for_record: str
    customer_letter: str | None = None
    field_provenance: dict[str, Provenance]


class SelectionCandidate(StrictModel):
    interaction_id: str
    channel: Literal["phone", "chat", "secure_message"]
    score: float
    features: dict[str, Any]
    stratum: str | None = None
    rank: int | None = None
    selection_reason: Literal["risk_ranked", "random_stratified"]


class SelectionRecord(StrictModel):
    schema_version: int = 1
    run_id: str
    review_id: str
    route: RouteDecision
    week_start: str
    week_end: str
    capacity: int
    risk_capacity: int
    random_capacity: int
    seed: int
    population_count: int
    risk_ranked_picks: list[str]
    random_stratified_picks: list[str]
    selected_reviews: list[str]
    candidates: list[SelectionCandidate]
    prohibited_features_checked: list[str]
    field_provenance: dict[str, Provenance]


class TerminationReason(StrEnum):
    ASSESSMENT_COMPLETE = "assessment_complete"
    BUDGET_EXHAUSTED = "budget_exhausted"
    WAITING_EXTERNAL = "waiting_external"
    LATEST_SAFE_TIME = "latest_safe_time"
    CONSERVATIVE_DEFAULT = "conservative_default"
    NO_PROGRESS = "no_progress"
    REPLAN_LIMIT = "replan_limit"
    ERROR = "error"
    CANCELLED = "cancelled"


class RunResult(StrictModel):
    run_id: str
    review_id: str
    status: Literal["complete", "suspended", "failed"]
    termination: TerminationReason
    assessment: AssessmentRecord | None
    event_count: int
    final_event_hash: str
    completed_at: datetime
