"""The complete ConductAI v1 event union and envelope."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from conductai.domain.models import Actor, StrictModel


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    NODE_ENTERED = "node_entered"
    NODE_EXITED = "node_exited"
    EDGE_TAKEN = "edge_taken"
    CHECKPOINT_SAVED = "checkpoint_saved"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    ROUTE_DECISION = "route_decision"
    PLAN_CREATED = "plan_created"
    PLAN_UPDATED = "plan_updated"
    TODO_UPDATED = "todo_updated"
    LLM_CALL_STARTED = "llm_call_started"
    LLM_STREAM_EVENT = "llm_stream_event"
    LLM_CALL = "llm_call"
    LLM_CALL_FAILED = "llm_call_failed"
    RETRY = "retry"
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_FINISHED = "subagent_finished"
    FANOUT_STARTED = "fanout_started"
    FANOUT_MERGED = "fanout_merged"
    SKILL_LOADED = "skill_loaded"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SQL_QUERY = "sql_query"
    RETRIEVAL = "retrieval"
    RETRIEVAL_DECISION = "retrieval_decision"
    GRAPH_QUERY = "graph_query"
    GRAPH_WRITE = "graph_write"
    MEMORY_READ = "memory_read"
    MEMORY_VERIFIED = "memory_verified"
    MEMORY_REJECTED = "memory_rejected"
    MEMORY_WRITE = "memory_write"
    MEMORY_SUPERSEDE = "memory_supersede"
    MEMORY_RETRACT = "memory_retract"
    MEMORY_CONSOLIDATE = "memory_consolidate"
    MEMORY_EXPIRE = "memory_expire"
    MEMORY_PURGE = "memory_purge"
    MEMORY_WRITE_SKIPPED = "memory_write_skipped"
    WRITE_REJECTED = "write_rejected"
    REVIEW_FILE_UPDATED = "review_file_updated"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    COMPUTATION = "computation"
    ARTIFACT_REQUESTED = "artifact_requested"
    ARTIFACT_ARRIVED = "artifact_arrived"
    CUSTOMER_OUTREACH_SENT = "customer_outreach_sent"
    PERSONA_REPLY = "persona_reply"
    COLLEAGUE_STATEMENT_ARRIVED = "colleague_statement_arrived"
    CLOCK_ADVANCED = "clock_advanced"
    WAIT_SUSPENDED = "wait_suspended"
    WAIT_RESUMED = "wait_resumed"
    TRANSCRIPT_ASSESSED = "transcript_assessed"
    SPEAKER_ATTRIBUTION_CHECKED = "speaker_attribution_checked"
    CONTRADICTION_DETECTED = "contradiction_detected"
    EVIDENCE_SPAN_VERIFIED = "evidence_span_verified"
    CITATION_VERIFIED = "citation_verified"
    FINDING_PROPOSED = "finding_proposed"
    FINDING_UPDATED = "finding_updated"
    UNTRUSTED_CONTENT_FLAGGED = "untrusted_content_flagged"
    REDACTION_APPLIED = "redaction_applied"
    FAIRNESS_CHECK = "fairness_check"
    ACCESS_DENIED = "access_denied"
    PANEL_STARTED = "panel_started"
    PANEL_POSITION = "panel_position"
    ADJUDICATION = "adjudication"
    VERIFIER_CHECK = "verifier_check"
    CONFIDENCE_COMPUTED = "confidence_computed"
    CONSERVATIVE_DEFAULT_APPLIED = "conservative_default_applied"
    ACTION_AUTHORIZED = "action_authorized"
    AUTOMATED_ACTION = "automated_action"
    ASSESSMENT_RECORDED = "assessment_recorded"
    BUDGET_UPDATE = "budget_update"
    NO_PROGRESS_DETECTED = "no_progress_detected"
    REPLAN_LIMIT_REACHED = "replan_limit_reached"
    TERMINATION = "termination"
    ERROR = "error"
    FALLBACK = "fallback"
    CANCELLED = "cancelled"
    EVALUATION_CHECK = "evaluation_check"


class RunEvent(StrictModel):
    schema_version: int = 1
    event_id: str
    run_id: str
    review_id: str
    seq: int = Field(gt=0)
    span_id: str
    parent_span_id: str | None = None
    branch_id: str | None = None
    checkpoint_id: str | None = None
    ts_wall: datetime
    ts_virtual: datetime
    actor: Actor
    type: EventType
    summary: str
    payload: dict[str, Any]
    refs: list[str]
    runtime: dict[str, Any]
    usage: dict[str, Any] | None = None
    redactions: list[dict[str, Any]]
    prev_event_hash: str | None = None
    event_hash: str
