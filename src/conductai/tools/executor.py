"""Central tool boundary: validation, authorization, events, and budgets."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Callable

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


class ToolExecutor:
    """No repository operation is reachable as an agent tool without paired events."""

    def __init__(self, repository: OperationalRepository, ledger: EventLedger) -> None:
        self._repository = repository
        self._ledger = ledger
        self._tools: dict[str, tuple[type[ToolArgs], Callable[..., Any]]] = {
            "get_route_facts": (InteractionArgs, repository.route_facts),
            "get_transcript": (InteractionArgs, repository.transcript),
            "get_credit_line_request": (InteractionArgs, repository.credit_request),
            "get_bureau_inquiry": (InquiryArgs, repository.bureau_inquiry),
            "retrieve_corpus_as_of": (CorpusArgs, repository.corpus_as_of),
        }

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
        for key in ("interaction_id", "turn_id", "credit_request_id", "inquiry_id", "doc_id"):
            if key in row and row[key] not in refs:
                refs.append(str(row[key]))
        for nested in row.values():
            if isinstance(nested, (dict, list)):
                for ref in _source_refs(nested):
                    if ref not in refs:
                        refs.append(ref)
    return refs
