"""Central tool boundary: validation, authorization, events, and budgets."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from conductai.data.repository import OperationalRepository
from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InteractionArgs(ToolArgs):
    interaction_id: str


class InquiryArgs(ToolArgs):
    credit_request_id: str


class CorpusArgs(ToolArgs):
    doc_id: str
    governing_date: str


class AccountArgs(ToolArgs):
    account_id: str


class ComplaintArgs(ToolArgs):
    complaint_id: str


class MemoryNoteArgs(ToolArgs):
    note_id: str


class ScannerRuleArgs(ToolArgs):
    rule_id: str


class MessageIdArgs(ToolArgs):
    message_id: str


class WorkstationClockOffsetArgs(ToolArgs):
    workstation_id: str


class PrecedentArgs(ToolArgs):
    precedent_id: str


class SearchPrecedentsArgs(ToolArgs):
    query: str
    as_of: str
    category: str | None = None
    top_k: int = 20


class SearchTranscriptsArgs(ToolArgs):
    query: str
    speaker: Literal["customer", "colleague"] | None = None
    from_at: str | None = None
    to_at: str | None = None
    top_k: int = 40


class RunRegisteredQueryArgs(ToolArgs):
    query_id: str
    parameters: dict[str, Any] = {}
    as_of: str
    row_limit: int = 1000


class RequestArtifactArgs(ToolArgs):
    artifact_id: str
    interaction_id: str
    kind: Literal["retranscription", "audio_recovery", "colleague_statement"]
    respond_by: str
    idempotency_key: str


class CallbackRequestArgs(ToolArgs):
    callback_request_id: str


class PreferenceArgs(ToolArgs):
    customer_id: str
    preference: str | None = None


class IncidentArgs(ToolArgs):
    incident_id: str


class AccountFlagArgs(ToolArgs):
    account_id: str
    flag: str | None = None


class InstallmentPlanArgs(ToolArgs):
    plan_id: str


class QueryGraphArgs(ToolArgs):
    template_id: str
    parameters: dict[str, Any] = {}
    as_of: str
    max_hops: int = 4
    limit: int = 250


class MessageCustomerArgs(ToolArgs):
    customer_id: str
    question: str
    respond_by: str
    idempotency_key: str


class ScheduleFollowUpArgs(ToolArgs):
    at: str
    action_type: str
    idempotency_key: str


class ToolExecutor:
    """No repository operation is reachable as an agent tool without paired events."""

    def __init__(
        self, repository: OperationalRepository, ledger: EventLedger,
        request_artifact: Callable[..., Any] | None = None,
        graph: Any | None = None,
        message_customer: Callable[..., Any] | None = None,
        schedule_follow_up: Callable[..., Any] | None = None,
    ) -> None:
        self._repository = repository
        self._ledger = ledger
        self._tools: dict[str, tuple[type[ToolArgs], Callable[..., Any]]] = {
            "get_route_facts": (InteractionArgs, repository.route_facts),
            "get_interaction": (InteractionArgs, repository.interaction),
            "get_transcript": (InteractionArgs, repository.transcript),
            "get_enrollments": (InteractionArgs, repository.enrollments),
            "get_desktop_events": (InteractionArgs, repository.desktop_events),
            "get_credit_line_request": (InteractionArgs, repository.credit_request),
            "get_bureau_inquiry": (InquiryArgs, repository.bureau_inquiry),
            "retrieve_corpus_as_of": (CorpusArgs, repository.corpus_as_of),
            "get_offers": (InteractionArgs, repository.offers),
            "get_fee_ledger": (AccountArgs, repository.fee_ledger_for_account),
            "get_complaint": (ComplaintArgs, repository.complaint),
            "get_memory_note": (MemoryNoteArgs, repository.memory_note),
            "get_scanner_rule": (ScannerRuleArgs, repository.scanner_rule),
            "get_workstation_clock_offset": (WorkstationClockOffsetArgs, repository.workstation_clock_offset),
            "get_precedent": (PrecedentArgs, repository.precedent),
            "search_precedents": (SearchPrecedentsArgs, repository.search_precedents),
            "search_transcripts": (SearchTranscriptsArgs, repository.search_transcripts),
            "run_registered_query": (RunRegisteredQueryArgs, repository.run_registered_query),
            "get_callback_request": (CallbackRequestArgs, repository.callback_request),
            "get_preference": (PreferenceArgs, repository.preference),
            "get_incident": (IncidentArgs, repository.incident),
            "get_account_flag": (AccountFlagArgs, repository.account_flag),
            "get_installment_plan": (InstallmentPlanArgs, repository.installment_plan),
            "get_crm_notes": (InteractionArgs, repository.crm_notes),
            "get_product_change": (InteractionArgs, repository.product_change),
            "get_internal_comm": (MessageIdArgs, repository.internal_comm),
        }
        if request_artifact is not None:
            self._tools["request_artifact"] = (RequestArtifactArgs, request_artifact)
        if graph is not None:
            self._tools["query_graph"] = (QueryGraphArgs, graph.query_graph)
        if message_customer is not None:
            self._tools["message_customer"] = (MessageCustomerArgs, message_customer)
        if schedule_follow_up is not None:
            self._tools["schedule_follow_up"] = (ScheduleFollowUpArgs, schedule_follow_up)

    @property
    def schemas(self) -> dict[str, dict[str, Any]]:
        return {name: schema.model_json_schema() for name, (schema, _) in self._tools.items()}

    def execute(
        self, name: str, raw_args: dict[str, Any], *, rationale: str, run_id: str,
        review_id: str, virtual_now: datetime, used: int, limit: int,
    ) -> tuple[Any, int]:
        if name not in self._tools:
            raise KeyError(name)
        if used >= limit:
            raise RuntimeError("tool-call budget exhausted")
        schema, function = self._tools[name]
        args = schema.model_validate(raw_args)
        span_id = f"SPN-{uuid.uuid4()}"
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="tool", name=name), type=EventType.TOOL_CALL,
            summary=f"Called {name}: {rationale}",
            payload={"tool": name, "version": 1, "rationale": rationale,
                     "args": args.model_dump(), "authorization": "passed"}, span_id=span_id,
        )
        started = time.perf_counter()
        try:
            result = function(**args.model_dump(), run_id=run_id, review_id=review_id, virtual_now=virtual_now)
        except Exception as exc:
            self._ledger.emit(
                run_id=run_id, review_id=review_id, virtual_now=virtual_now,
                actor=Actor(kind="tool", name=name), type=EventType.TOOL_RESULT,
                summary=f"{name} failed with {type(exc).__name__}",
                payload={"tool": name, "status": "error", "error_class": type(exc).__name__,
                         "message": "redacted", "duration_ms": round((time.perf_counter() - started) * 1000, 3)},
                span_id=span_id,
            )
            self._ledger.emit(
                run_id=run_id, review_id=review_id, virtual_now=virtual_now,
                actor=Actor(kind="tool", name=name), type=EventType.ERROR,
                summary=f"Tool boundary failed: {name}",
                payload={"operation": name, "class": type(exc).__name__, "message": "redacted", "terminal": False},
                span_id=span_id,
            )
            raise
        refs = _source_refs(result)
        blob = self._ledger.put_blob(result)
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="tool", name=name), type=EventType.TOOL_RESULT,
            summary=f"{name} returned {len(refs)} source reference(s)",
            payload={"tool": name, "status": "ok", "result_blob": blob,
                     "source_ids": refs, "duration_ms": round((time.perf_counter() - started) * 1000, 3)},
            refs=refs, span_id=span_id,
        )
        used += 1
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="runtime", name="budget_service"), type=EventType.BUDGET_UPDATE,
            summary=f"Tool budget: {used} of {limit} used",
            payload={"dimension": "tool_calls", "used": used, "limit": limit, "remaining": limit - used},
        )
        return result, used


def _source_refs(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    refs: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "source_id" in row:
            refs.append(str(row["source_id"]))
            continue
        for key in (
            "interaction_id", "turn_id", "credit_request_id", "inquiry_id", "doc_id",
            "enrollment_id", "event_id", "artifact_id", "offer_instance_id", "ledger_id",
            "complaint_id", "note_id", "rule_id", "precedent_id", "workstation_id",
            "callback_request_id", "pref_id", "incident_id", "flag_id", "plan_id",
        ):
            if key in row and row[key] not in refs:
                refs.append(str(row[key]))
        for nested in row.values():
            if isinstance(nested, (dict, list)):
                for ref in _source_refs(nested):
                    if ref not in refs:
                        refs.append(ref)
    return refs
