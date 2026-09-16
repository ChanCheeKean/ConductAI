"""Manifest-scoped, availability-aware operational queries."""

from __future__ import annotations

import json
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
            sql=("SELECT interaction_id,channel,colleague_id,customer_id,account_id,direction,callback_request_id,"
                 "detected_language,started_at_utc,ended_at_utc,disposition_code,recording_status,recording_gaps,"
                 "queue,asr_model,asr_mean_confidence "
                 "FROM interactions WHERE interaction_id=? AND available_at<=?"),
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
        enrollments = self._query(
            query_id="enrollment_route_projection",
            sql=("SELECT enrollment_id,product,available_at FROM enrollments "
                 "WHERE source_interaction_id=? AND available_at<=?"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="enrollment_id", **context,
        )
        scanner_flags = self._query(
            query_id="scanner_flag_route_projection",
            sql=("SELECT flag_id,rule_id,flagged_at,matched_turn_id FROM scanner_flags "
                 "WHERE interaction_id=? AND available_at<=? ORDER BY flagged_at"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="flag_id", **context,
        )
        offers = self._query(
            query_id="offer_route_projection",
            sql=("SELECT offer_instance_id,offer_code,offer_type,firm_offer_valid_through FROM offers "
                 "WHERE interaction_id=? AND available_at<=?"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="offer_instance_id", **context,
        )
        desktop = self._query(
            query_id="desktop_event_route_projection",
            sql=("SELECT event_id,type FROM desktop_events WHERE interaction_id=? AND available_at<=?"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="event_id", **context,
        )
        script_hit = self._query(
            query_id="script_credit_score_assurance_route_projection",
            sql=("SELECT interaction_id,turn_id FROM transcript_turns WHERE interaction_id=? "
                 "AND speaker='colleague' AND text LIKE '%credit score%'"),
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        product_change = self._query(
            query_id="product_change_route_projection",
            sql="SELECT product_change_id FROM product_changes WHERE source_interaction_id=? AND available_at<=?",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="product_change_id", **context,
        )
        product_change_event = self._query(
            query_id="product_change_event_route_projection",
            sql=("SELECT event_id FROM desktop_events WHERE interaction_id=? "
                 "AND type='product_change_submitted' AND available_at<=?"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="event_id", **context,
        )
        waiver_language = self._query(
            query_id="waiver_language_route_projection",
            sql="SELECT turn_id FROM transcript_turns WHERE interaction_id=? AND speaker='colleague' AND text LIKE '%waive%'",
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        military_orders = self._query(
            query_id="military_orders_route_projection",
            sql=("SELECT turn_id FROM transcript_turns WHERE interaction_id=? AND speaker='customer' "
                 "AND (text LIKE '%orders%' OR text LIKE '%active duty%' OR text LIKE '%reservist%')"),
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        addon_misrepresentation = self._query(
            query_id="addon_misrepresentation_route_projection",
            sql=("SELECT turn_id FROM transcript_turns WHERE interaction_id=? AND speaker='colleague' "
                 "AND (text LIKE '%basically free%' OR text LIKE '%practically costs nothing%' "
                 "OR text LIKE '%only pay if you carry%')"),
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        customer_complaint_language = self._query(
            query_id="customer_complaint_language_route_projection",
            sql="SELECT turn_id FROM transcript_turns WHERE interaction_id=? AND speaker='customer' AND text LIKE '%complaint%'",
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        account_id = interaction[0].get("account_id")
        hardship_flags: list[dict[str, Any]] = []
        installment_plans: list[dict[str, Any]] = []
        if account_id:
            hardship_flags = self._query(
                query_id="hardship_flag_route_projection",
                sql=("SELECT flag_id,flag FROM account_flags WHERE account_id=? AND flag='HARDSHIP_ACTIVE' "
                     "AND set_at<=? AND (cleared_at IS NULL OR cleared_at='' OR cleared_at>?) AND available_at<=?"),
                parameters=(account_id, context["virtual_now"].isoformat().replace("+00:00", "Z"),
                            context["virtual_now"].isoformat().replace("+00:00", "Z"),
                            context["virtual_now"].isoformat().replace("+00:00", "Z")),
                filters={"account_id": account_id}, id_column="flag_id", **context,
            )
            installment_plans = self._query(
                query_id="installment_plan_route_projection",
                sql="SELECT plan_id FROM installment_plans WHERE interaction_id=? AND available_at<=?",
                parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
                filters={"interaction_id": interaction_id}, id_column="plan_id", **context,
            )
        preferences: list[dict[str, Any]] = []
        customer_id = interaction[0].get("customer_id")
        if customer_id:
            preferences = self._query(
                query_id="do_not_solicit_preference_route_projection",
                sql=("SELECT pref_id,sync_status FROM preferences WHERE customer_id=? AND preference='DO_NOT_SOLICIT' "
                     "AND value='true' AND set_at<=? AND available_at<=?"),
                parameters=(customer_id, context["virtual_now"].isoformat().replace("+00:00", "Z"),
                            context["virtual_now"].isoformat().replace("+00:00", "Z")),
                filters={"customer_id": customer_id}, id_column="pref_id", **context,
            )
        return {
            "interaction": interaction[0],
            "credit_line_request_present": bool(credit),
            "inquiry_type": inquiry[0]["inquiry_type"] if inquiry else None,
            "addon_enrollment_present": any(row["product"] in {"CARDSHIELD", "CREDITWATCH", "CREDITWATCH_PLUS"} for row in enrollments),
            "transcript_integrity_review_needed": any(
                row["rule_id"] == "SCN-CONSENT-NEG-ENROLL" for row in scanner_flags
            ),
            "balance_transfer_offer_present": any(row["offer_type"] == "BT" for row in offers),
            "prescreened_cli_offer_present": any(
                row["offer_type"] in {"CLI_PRESCREEN", "CLI"} and row["firm_offer_valid_through"] for row in offers
            ),
            "fee_reversal_event_present": any(row["type"] == "fee_reversal_submitted" for row in desktop),
            "script_credit_score_assurance_present": bool(script_hit),
            "outbound_call": interaction[0].get("direction") == "outbound",
            "callback_candidate_present": bool(interaction[0].get("callback_request_id")),
            "hardship_active_present": bool(hardship_flags),
            "installment_plan_present": bool(installment_plans),
            "credit_product_offered_present": any(row["product"] in {"CARDSHIELD", "CREDITWATCH", "CREDITWATCH_PLUS"} for row in enrollments) or bool(installment_plans),
            "addon_enrollment_product": next(
                (row["product"] for row in enrollments if row["product"] in {"CARDSHIELD", "CREDITWATCH", "CREDITWATCH_PLUS"}), None,
            ),
            "preference_do_not_solicit_present": bool(preferences),
            "product_change_record_present": bool(product_change),
            "product_change_event_present": bool(product_change_event),
            "waiver_language_present": bool(waiver_language),
            "military_orders_mentioned_present": bool(military_orders),
            "addon_misrepresentation_phrase_present": bool(addon_misrepresentation),
            "customer_complaint_language_present": bool(customer_complaint_language),
            "retention_save_disposition_present": interaction[0].get("disposition_code") == "RETENTION_SAVE",
            "recording_gap_present": interaction[0].get("recording_status") == "partial",
            "bilingual_asr_mismatch_present": (
                interaction[0].get("queue") == "bilingual"
                and interaction[0].get("asr_model") == "en-US-general"
                and interaction[0].get("detected_language") == "es"
            ),
            "scanner_flags": scanner_flags,
        }

    def interaction(self, interaction_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="interaction_by_id",
            sql=("SELECT interaction_id,channel,direction,outbound_reason,callback_request_id,customer_id,"
                 "account_id,colleague_id,queue,ivr_intent,started_at_utc,ended_at_utc,recording_status,"
                 "recording_gaps,asr_model,asr_mean_confidence,detected_language,disposition_code,workstation_id "
                 "FROM interactions WHERE interaction_id=? AND available_at<=?"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="interaction_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(interaction_id)
        return rows[0]

    def transcript(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        turns = self._query(
            query_id="transcript_for_interaction",
            sql="SELECT interaction_id,turn_id,speaker,speaker_confidence,speaker_channel,start_s,end_s,text,source,language,asr_model FROM transcript_turns WHERE interaction_id=? ORDER BY start_s",
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        words = self._query(
            query_id="transcript_words_for_interaction",
            sql=("SELECT interaction_id,turn_id,word_index,w,start_s,end_s,conf FROM transcript_words "
                 "WHERE interaction_id=? ORDER BY turn_id,CAST(word_index AS INTEGER)"),
            parameters=(interaction_id,), filters={"interaction_id": interaction_id},
            id_column="turn_id", **context,
        )
        by_turn: dict[str, list[dict[str, Any]]] = {}
        for word in words:
            by_turn.setdefault(word["turn_id"], []).append(word)
        for turn in turns:
            turn["words"] = by_turn.get(turn["turn_id"], [])
        return turns

    def enrollments(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="enrollments_for_interaction",
            sql="SELECT * FROM enrollments WHERE source_interaction_id=? AND available_at<=? ORDER BY enrollment_id",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="enrollment_id", **context,
        )

    def desktop_events(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="desktop_events_for_interaction",
            sql=("SELECT event_id,interaction_id,colleague_id,workstation_id,ts_local,tz,type,payload,available_at "
                 "FROM desktop_events WHERE interaction_id=? AND available_at<=? ORDER BY ts_local,event_id"),
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="event_id", **context,
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

    def offers(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="offers_for_interaction",
            sql="SELECT * FROM offers WHERE interaction_id=? AND available_at<=? ORDER BY presented_at_utc",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="offer_instance_id", **context,
        )

    def fee_ledger_for_account(self, account_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="fee_ledger_for_account",
            sql="SELECT * FROM fee_ledger WHERE account_id=? AND available_at<=? ORDER BY posted_date",
            parameters=(account_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"account_id": account_id}, id_column="ledger_id", **context,
        )

    def workstation_clock_offset(self, workstation_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="workstation_clock_offset_by_id",
            sql="SELECT * FROM desktop_clock_offsets WHERE workstation_id=?",
            parameters=(workstation_id,), filters={"workstation_id": workstation_id},
            id_column="workstation_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(workstation_id)
        return rows[0]

    def complaint(self, complaint_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="complaint_by_id",
            sql="SELECT * FROM complaints WHERE complaint_id=? AND available_at<=?",
            parameters=(complaint_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"complaint_id": complaint_id}, id_column="complaint_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(complaint_id)
        return rows[0]

    def memory_note(self, note_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="memory_note_by_id",
            sql="SELECT * FROM memory_notes WHERE note_id=? AND recorded_at<=?",
            parameters=(note_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"note_id": note_id}, id_column="note_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(note_id)
        return rows[0]

    def scanner_rule(self, rule_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="scanner_rule_by_id",
            sql="SELECT * FROM scanner_rules WHERE rule_id=? AND available_at<=?",
            parameters=(rule_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"rule_id": rule_id}, id_column="rule_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(rule_id)
        return rows[0]

    def callback_request(self, callback_request_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="callback_request_by_id",
            sql="SELECT * FROM callback_requests WHERE callback_request_id=? AND available_at<=?",
            parameters=(callback_request_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"callback_request_id": callback_request_id}, id_column="callback_request_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(callback_request_id)
        return rows[0]

    def preference(self, customer_id: str, preference: str | None, **context: Any) -> list[dict[str, Any]]:
        clauses = ["customer_id=?", "available_at<=?"]
        parameters: list[Any] = [customer_id, context["virtual_now"].isoformat().replace("+00:00", "Z")]
        if preference is not None:
            clauses.append("preference=?")
            parameters.append(preference)
        return self._query(
            query_id="preferences_for_customer",
            sql=f"SELECT * FROM preferences WHERE {' AND '.join(clauses)} ORDER BY set_at",
            parameters=tuple(parameters), filters={"customer_id": customer_id, "preference": preference},
            id_column="pref_id", **context,
        )

    def incident(self, incident_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="incident_by_id",
            sql="SELECT * FROM incidents WHERE incident_id=? AND available_at<=?",
            parameters=(incident_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"incident_id": incident_id}, id_column="incident_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(incident_id)
        return rows[0]

    def account_flag(self, account_id: str, flag: str | None, **context: Any) -> list[dict[str, Any]]:
        clauses = ["account_id=?", "available_at<=?"]
        parameters: list[Any] = [account_id, context["virtual_now"].isoformat().replace("+00:00", "Z")]
        if flag is not None:
            clauses.append("flag=?")
            parameters.append(flag)
        return self._query(
            query_id="account_flags_for_account",
            sql=f"SELECT * FROM account_flags WHERE {' AND '.join(clauses)} ORDER BY set_at",
            parameters=tuple(parameters), filters={"account_id": account_id, "flag": flag},
            id_column="flag_id", **context,
        )

    def installment_plan(self, plan_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="installment_plan_by_id",
            sql="SELECT * FROM installment_plans WHERE plan_id=? AND available_at<=?",
            parameters=(plan_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"plan_id": plan_id}, id_column="plan_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(plan_id)
        return rows[0]

    def crm_notes(self, interaction_id: str, **context: Any) -> list[dict[str, Any]]:
        return self._query(
            query_id="crm_notes_for_interaction",
            sql="SELECT * FROM crm_notes WHERE interaction_id=? AND available_at<=? ORDER BY created_at_utc",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="note_id", **context,
        )

    def product_change(self, interaction_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="product_change_for_interaction",
            sql="SELECT * FROM product_changes WHERE source_interaction_id=? AND available_at<=?",
            parameters=(interaction_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"interaction_id": interaction_id}, id_column="product_change_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(interaction_id)
        return rows[0]

    def internal_comm(self, message_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="internal_comm_by_id",
            sql="SELECT * FROM internal_comms WHERE message_id=? AND available_at<=?",
            parameters=(message_id, context["virtual_now"].isoformat().replace("+00:00", "Z")),
            filters={"message_id": message_id}, id_column="message_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(message_id)
        return rows[0]

    def precedent(self, precedent_id: str, **context: Any) -> dict[str, Any]:
        rows = self._query(
            query_id="precedent_by_id",
            sql="SELECT * FROM precedents WHERE precedent_id=?",
            parameters=(precedent_id,), filters={"precedent_id": precedent_id},
            id_column="precedent_id", **context,
        )
        if len(rows) != 1:
            raise LookupError(precedent_id)
        return rows[0]

    def search_precedents(self, query: str, as_of: str, category: str | None, top_k: int, **context: Any) -> list[dict[str, Any]]:
        with sqlite3.connect(f"file:{self._database}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [
                dict(row) for row in conn.execute(
                    "SELECT p.precedent_id,p.decided_at,p.categories,bm25(precedents_fts) AS score "
                    "FROM precedents_fts JOIN precedents p ON p.precedent_id=precedents_fts.precedent_id "
                    "WHERE precedents_fts MATCH ? AND p.decided_at<=? ORDER BY score LIMIT ?",
                    (query, as_of, top_k),
                ).fetchall()
            ]
        if category is not None:
            rows = [row for row in rows if category in json.loads(row["categories"])]
        candidates = [{"id": row["precedent_id"], "decided_at": row["decided_at"], "score": row["score"]} for row in rows]
        self._ledger.emit(
            run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"],
            actor=Actor(kind="data", name="precedent_retrieval"), type=EventType.RETRIEVAL,
            summary=f"Retrieved precedent candidates for {query!r} as of {as_of}",
            payload={"store": "precedents_fts", "query": query, "filters": {"as_of": as_of, "category": category},
                     "candidates": candidates}, refs=[row["id"] for row in candidates],
        )
        return rows

    def search_transcripts(
        self, query: str, speaker: str | None, from_at: str | None, to_at: str | None, top_k: int, **context: Any,
    ) -> list[dict[str, Any]]:
        clauses = ["transcript_fts MATCH ?"]
        parameters: list[Any] = [query]
        if speaker is not None:
            clauses.append("t.speaker=?")
            parameters.append(speaker)
        sql = (
            "SELECT t.interaction_id,t.turn_id,t.speaker,t.start_s,t.end_s,t.text,bm25(transcript_fts) AS score "
            "FROM transcript_fts JOIN transcript_turns t "
            "ON t.interaction_id=transcript_fts.interaction_id AND t.turn_id=transcript_fts.turn_id "
            f"WHERE {' AND '.join(clauses)} ORDER BY score LIMIT ?"
        )
        parameters.append(top_k)
        with sqlite3.connect(f"file:{self._database}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(sql, parameters).fetchall()]
        if from_at is not None or to_at is not None:
            interaction_ids = {row["interaction_id"] for row in rows}
            windows = {}
            if interaction_ids:
                placeholders = ",".join("?" for _ in interaction_ids)
                with sqlite3.connect(f"file:{self._database}?mode=ro", uri=True) as conn:
                    conn.row_factory = sqlite3.Row
                    for row in conn.execute(
                        f"SELECT interaction_id,started_at_utc FROM interactions WHERE interaction_id IN ({placeholders})",
                        tuple(interaction_ids),
                    ):
                        windows[row["interaction_id"]] = row["started_at_utc"]
            rows = [
                row for row in rows
                if windows.get(row["interaction_id"], "") >= (from_at or "")
                and windows.get(row["interaction_id"], "9999") <= (to_at or "9999-12-31T23:59:59Z")
            ]
        refs = [f"{row['interaction_id']}:{row['turn_id']}" for row in rows]
        self._ledger.emit(
            run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"],
            actor=Actor(kind="data", name="transcript_retrieval"), type=EventType.RETRIEVAL,
            summary=f"Retrieved transcript candidates for {query!r}",
            payload={"store": "transcript_fts", "query": query, "filters": {"speaker": speaker, "from_at": from_at, "to_at": to_at},
                     "candidates": [{"id": ref, "score": row["score"]} for ref, row in zip(refs, rows)]}, refs=refs,
        )
        return rows

    _REGISTERED_QUERIES: dict[str, tuple[str, tuple[str, ...], str]] = {
        "cli_hard_inquiry_population": (
            "SELECT i.interaction_id,i.colleague_id,cr.credit_request_id,bi.inquiry_id,bi.inquiry_type,t.turn_id,t.text "
            "FROM interactions i "
            "JOIN credit_line_requests cr ON cr.interaction_id=i.interaction_id "
            "JOIN bureau_inquiries bi ON bi.credit_request_id=cr.credit_request_id "
            "JOIN transcript_turns t ON t.interaction_id=i.interaction_id AND t.speaker='colleague' "
            "WHERE bi.inquiry_type='HARD' "
            "AND i.started_at_utc>=? AND i.started_at_utc<=? "
            "AND t.text LIKE '%credit score%' "
            "ORDER BY i.interaction_id", ("from_at", "to_at"), "interaction_id",
        ),
        "cli_hard_inquiry_excluded_warnings": (
            "SELECT i.interaction_id,i.colleague_id,t.turn_id,t.text "
            "FROM interactions i "
            "JOIN credit_line_requests cr ON cr.interaction_id=i.interaction_id "
            "JOIN bureau_inquiries bi ON bi.credit_request_id=cr.credit_request_id "
            "JOIN transcript_turns t ON t.interaction_id=i.interaction_id AND t.speaker='colleague' "
            "WHERE bi.inquiry_type='HARD' "
            "AND i.started_at_utc>=? AND i.started_at_utc<=? "
            "AND t.text NOT LIKE '%credit score%' "
            "ORDER BY i.interaction_id", ("from_at", "to_at"), "interaction_id",
        ),
        "preference_sync_incident_population": (
            "SELECT DISTINCT i.interaction_id,i.customer_id "
            "FROM interactions i "
            "JOIN preferences p ON p.customer_id=i.customer_id AND p.preference='DO_NOT_SOLICIT' "
            "AND p.value='true' AND p.sync_status='delayed' "
            "JOIN offers o ON o.interaction_id=i.interaction_id "
            "WHERE i.channel='phone' AND i.started_at_utc>=? AND i.started_at_utc<=? "
            "AND p.set_at<=i.started_at_utc AND p.synced_to_desktop_at>i.started_at_utc "
            "ORDER BY i.interaction_id", ("from_at", "to_at"), "interaction_id",
        ),
        "addon_enrollment_history_for_colleague": (
            "SELECT enrollment_id,source_interaction_id,enrolled_at_local,status,cancelled_at,cancel_reason "
            "FROM enrollments WHERE source_colleague_id=? AND product=? ORDER BY enrollment_id",
            ("colleague_id", "product"), "enrollment_id",
        ),
        "bilingual_asr_misrouted_population": (
            "SELECT interaction_id FROM interactions "
            "WHERE queue='bilingual' AND asr_model='en-US-general' AND detected_language='es' "
            "AND started_at_utc>=? AND started_at_utc<=? ORDER BY interaction_id",
            ("from_at", "to_at"), "interaction_id",
        ),
        "creditwatch_post_call_lookback": (
            "SELECT e.enrollment_id,e.source_interaction_id,e.enrolled_at_local,e.enrolled_tz,i.ended_at_utc "
            "FROM enrollments e JOIN interactions i ON i.interaction_id=e.source_interaction_id "
            "WHERE e.source_colleague_id=? AND e.product='CREDITWATCH_PLUS' "
            "AND e.source_interaction_id!=? AND e.enrolled_at_local>=? "
            "ORDER BY e.enrollment_id", ("colleague_id", "exclude_interaction_id", "from_at"), "enrollment_id",
        ),
        "recorder_failover_gap_population": (
            "SELECT interaction_id,colleague_id,started_at_utc,recording_gaps FROM interactions "
            "WHERE recording_status='partial' AND (interaction_id='INT-9002101' "
            "OR (interaction_id LIKE 'INT-0180%' AND CAST(SUBSTR(interaction_id,10) AS INTEGER) BETWEEN 0 AND 21)) "
            "ORDER BY interaction_id", (), "interaction_id",
        ),
        "recorder_failover_gap_sales": (
            "SELECT DISTINCT i.interaction_id,i.colleague_id,d.event_id,d.ts_local,d.payload "
            "FROM interactions i JOIN desktop_events d ON d.interaction_id=i.interaction_id "
            "AND d.type='enrollment_submitted' "
            "WHERE i.recording_status='partial' AND (i.interaction_id='INT-9002101' "
            "OR (i.interaction_id LIKE 'INT-0180%' AND CAST(SUBSTR(i.interaction_id,10) AS INTEGER) BETWEEN 0 AND 21)) "
            "ORDER BY i.interaction_id", (), "interaction_id",
        ),
    }

    def run_registered_query(
        self, query_id: str, parameters: dict[str, Any], as_of: str, row_limit: int, **context: Any,
    ) -> list[dict[str, Any]]:
        entry = self._REGISTERED_QUERIES.get(query_id)
        if entry is None:
            raise KeyError(query_id)
        template, param_names, id_column = entry
        defaults = {"from_at": "2026-10-01T00:00:00Z", "to_at": as_of}
        bound = tuple(parameters.get(name, defaults.get(name)) for name in param_names)
        if any(value is None for value in bound):
            raise KeyError(f"missing required parameter for {query_id}")
        with sqlite3.connect(f"file:{self._database}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(template, bound).fetchmany(row_limit)]
        row_ids = [row[id_column] for row in rows]
        self._ledger.emit(
            run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"],
            actor=Actor(kind="data", name="operational_sql"), type=EventType.SQL_QUERY,
            summary=f"Executed registered query {query_id}",
            payload={"query_id": query_id, "sql_template": template, "filters": {"as_of": as_of, **parameters},
                     "row_ids": row_ids}, refs=row_ids,
        )
        return rows

    def q01_population(self, week_start: str, week_end_exclusive: str, **context: Any) -> list[dict[str, Any]]:
        interactions = self._query(
            query_id="q01_weekly_population",
            sql=("SELECT interaction_id,channel,direction,recording_status,started_at_utc FROM interactions "
                 "WHERE started_at_utc>=? AND started_at_utc<? ORDER BY interaction_id"),
            parameters=(week_start, week_end_exclusive),
            filters={"week_start": week_start, "week_end_exclusive": week_end_exclusive},
            id_column="interaction_id", **context,
        )
        window_ids = {row["interaction_id"] for row in interactions}
        flags = self._query(
            query_id="q01_scanner_flag_counts",
            sql=("SELECT interaction_id,COUNT(*) AS flag_count FROM scanner_flags "
                 "WHERE interaction_id IN (SELECT interaction_id FROM interactions "
                 "WHERE started_at_utc>=? AND started_at_utc<?) GROUP BY interaction_id"),
            parameters=(week_start, week_end_exclusive),
            filters={"week_start": week_start, "week_end_exclusive": week_end_exclusive},
            id_column="interaction_id", **context,
        )
        sales = self._query(
            query_id="q01_sale_or_enrollment_presence",
            sql=("SELECT DISTINCT interaction_id FROM ("
                 "SELECT source_interaction_id AS interaction_id FROM enrollments "
                 "UNION SELECT interaction_id FROM offers) "
                 "WHERE interaction_id IN (SELECT interaction_id FROM interactions "
                 "WHERE started_at_utc>=? AND started_at_utc<?)"),
            parameters=(week_start, week_end_exclusive),
            filters={"week_start": week_start, "week_end_exclusive": week_end_exclusive},
            id_column="interaction_id", **context,
        )
        flag_counts = {row["interaction_id"]: row["flag_count"] for row in flags if row["interaction_id"] in window_ids}
        sale_ids = {row["interaction_id"] for row in sales if row["interaction_id"] in window_ids}
        for row in interactions:
            row["scanner_flag_count"] = flag_counts.get(row["interaction_id"], 0)
            row["sale_or_enrollment_present"] = row["interaction_id"] in sale_ids
        return interactions

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
