"""Manifest-scoped, availability-aware operational queries."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger


FORBIDDEN_RESOURCE_PARTS = {"ground_truth", "simulation", "on_request", "is_hero"}


class AccessDenied(PermissionError):
    pass


class OperationalRepository:
    """Exposes only registered queries; callers never receive a SQLite handle."""

    def __init__(self, database: Path, ledger: EventLedger) -> None:
        self._database = database.resolve()
        self._ledger = ledger

    def guard_resource(self, resource: str, *, run_id: str, review_id: str, virtual_now: datetime) -> None:
        normalized = resource.lower().replace("\\", "/")
        if any(part in normalized for part in FORBIDDEN_RESOURCE_PARTS):
            self._ledger.emit(
                run_id=run_id, review_id=review_id, virtual_now=virtual_now,
                actor=Actor(kind="data", name="access_guard"), type=EventType.ACCESS_DENIED,
                summary="Denied access to a restricted evaluator or harness resource",
                payload={"resource": resource, "rule": "agent_view_only"},
            )
            raise AccessDenied(resource)

    def _query(
        self, *, query_id: str, sql: str, parameters: tuple[Any, ...], run_id: str,
        review_id: str, virtual_now: datetime, filters: dict[str, Any], id_column: str,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(f"file:{self._database}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(sql, parameters).fetchall()]
        row_ids = [str(row[id_column]) for row in rows]
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="data", name="operational_sql"), type=EventType.SQL_QUERY,
            summary=f"Executed registered query {query_id}",
            payload={"query_id": query_id, "sql_template": sql, "filters": filters, "row_ids": row_ids},
            refs=row_ids,
        )
        return rows

    def route_facts(self, interaction_id: str, **context: Any) -> dict[str, Any]:
        interaction = self._query(
            query_id="interaction_route_projection",
            sql="SELECT interaction_id,channel,colleague_id,detected_language,started_at_utc FROM interactions WHERE interaction_id=? AND available_at<=?",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id, "available_at_lte": context["virtual_now"].isoformat()},
            id_column="interaction_id", **context,
        )
        if len(interaction) != 1:
            raise LookupError(interaction_id)
        credit = self._query(
            query_id="credit_request_route_projection",
            sql="SELECT credit_request_id,interaction_id FROM credit_line_requests WHERE interaction_id=? AND available_at<=?",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="credit_request_id", **context,
        )
        inquiry: list[dict[str, Any]] = []
        if credit:
            inquiry = self._query(
                query_id="bureau_inquiry_route_projection",
                sql="SELECT inquiry_id,inquiry_type FROM bureau_inquiries WHERE credit_request_id=? AND available_at<=?",
                parameters=(credit[0]["credit_request_id"], context["virtual_now"].isoformat().replace("+00:00", "Z")),
                filters={"credit_request_id": credit[0]["credit_request_id"]}, id_column="inquiry_id", **context,
            )
        return {
            "interaction": interaction[0],
            "credit_line_request_present": bool(credit),
            "inquiry_type": inquiry[0]["inquiry_type"] if inquiry else None,
        }

    def transcript(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="transcript_for_interaction",
            sql="SELECT interaction_id,turn_id,speaker,speaker_confidence,speaker_channel,start_s,end_s,text,source,language,asr_model FROM transcript_turns WHERE interaction_id=? ORDER BY start_s",
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )

    def credit_request(self, interaction_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="credit_request_for_interaction",
            sql="SELECT * FROM credit_line_requests WHERE interaction_id=? AND available_at<=?",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="credit_request_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(interaction_id)
        return rows[0]

    def bureau_inquiry(self, credit_request_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="bureau_inquiry_for_request",
            sql="SELECT * FROM bureau_inquiries WHERE credit_request_id=? AND available_at<=?",
            parameters=(credit_request_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"credit_request_id": credit_request_id}, id_column="inquiry_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(credit_request_id)
        return rows[0]

    def corpus_as_of(self, doc_id: str, governing_date: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="corpus_document_as_of",
            sql=("SELECT doc_id,version,title,family,effective_from,effective_to,status,body "
                 "FROM corpus_documents WHERE doc_id=? AND effective_from<=? "
                 "AND (effective_to='' OR effective_to>=?) ORDER BY effective_from DESC LIMIT 1"),
            parameters=(doc_id, governing_date, governing_date),
            filters={"doc_id": doc_id, "as_of": governing_date, "status": ["active", "superseded_as_of"]},
            id_column="doc_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(f"{doc_id} as of {governing_date}")
        row = rows[0]
        row["source_id"] = f"{row['doc_id']}@{row['version']}"
        self._ledger.emit(
            run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"],
            actor=Actor(kind="data", name="corpus_retrieval"), type=EventType.RETRIEVAL,
            summary="Retrieved the policy version governing the interaction date",
            payload={"store": "corpus_exact", "query": doc_id, "filters": {"as_of": governing_date},
                     "candidates": [{"id": row["source_id"], "effective_from": row["effective_from"]}]},
            refs=[row["source_id"]],
        )
        return row
