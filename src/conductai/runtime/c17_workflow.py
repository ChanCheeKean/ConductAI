"""C17 retention bargain: a specific numeric credit-score prediction and an unrequested retention credit that
was used to talk a customer out of closing an account, without ever processing either explicit cancellation
request. A deadline computed in the sandbox (the annual-fee refund window) and a customer-outreach wait gate
whether the closure is honored now.

Note: the design catalog cites PRE-0044 as the controlling MC-06 precedent, but PRE-0044 does not exist in this
dataset (only PRE-0001 through PRE-0040 do). PRE-0016 is used instead: it is the actual precedent in
`precedents` with categories ["MC-06"] and outcome {colleague: substantiated, control: none, customer:
substantiated}, matching the "cancellation not processed" fact pattern this case needs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.deadlines import latest_safe_decision
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C17Workflow:
    """Deterministic retention-bargain path with a customer-outreach wait; C17 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=45, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "retention_cancellation_review":
            raise RuntimeError("C17 requires the retention_cancellation_review route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the retention-cancellation review path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "retention_save_disposition_present": state["route_facts"]["retention_save_disposition_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        for skill in route.skills:
            metadata, digest, path = load_skill(self.root, skill)
            self.ledger.emit(
                **node_context(state), actor=Actor(kind="agent", name="skill_backend"),
                type=EventType.SKILL_LOADED, summary=f"Loaded {skill} for the selected route",
                payload={"skill": skill, "version": metadata["version"], "hash": digest,
                         "path": path, "reason": "route"}, refs=[path],
            )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq}

    def integrity(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the full call for both cancellation requests, the numeric credit-score claim, and the "
                       "retention offer",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the credit-score claim is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        used = state["tool_calls_used"]
        governing_date = interaction["started_at_utc"][:10]
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": interaction["account_id"]},
            rationale="Confirm the posted annual fee and the retention credit applied on this call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        annual_fee = next(row for row in fee_ledger if row["type"] == "ANNUAL_FEE")
        retention_credit = next(row for row in fee_ledger if row["type"] == "RETENTION_CREDIT")
        discard_candidates, used = self.tools.execute(
            "search_precedents", {"query": "closing credit factors", "as_of": governing_date, "top_k": 5},
            rationale="Find prior decisions about closing and general credit-score factors",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        discarded_precedent, used = self.tools.execute(
            "get_precedent", {"precedent_id": discard_candidates[0]["precedent_id"]},
            rationale="Retrieve the leading precedent candidate to check whether it controls this fact pattern",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        retain_candidates, used = self.tools.execute(
            "search_precedents", {"query": "evidence weighed policy effective", "as_of": governing_date,
                                   "category": "MC-06", "top_k": 20},
            rationale="Find prior decisions about a servicing cancellation request that was never processed",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        retained_id = next(row["precedent_id"] for row in retain_candidates if row["precedent_id"] == "PRE-0016")
        retained_precedent, used = self.tools.execute(
            "get_precedent", {"precedent_id": retained_id},
            rationale="Retrieve PRE-0016 to confirm it controls the unprocessed-cancellation finding",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        decision = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="policy_analyst"),
            type=EventType.RETRIEVAL_DECISION,
            summary="Distinguished PRE-0017 and retained PRE-0016 for the unprocessed cancellation",
            payload={"used": [{"id": retained_precedent["precedent_id"],
                                "why": "MC-06 cancellation not honored; the design catalog cites PRE-0044, which "
                                       "does not exist in this dataset, so PRE-0016 is used as the controlling "
                                       "MC-06 precedent"}],
                     "discarded": [{"id": discarded_precedent["precedent_id"],
                                    "why": "PRE-0017 held that a general utilization/history caution was no_error; "
                                           "this call's specific hundred-point prediction is a distinguishable, "
                                           "unprotected fact pattern"}]},
            refs=[discarded_precedent["precedent_id"], retained_precedent["precedent_id"]],
        )
        evidence = {**state["evidence"], "fee_ledger": fee_ledger, "annual_fee": annual_fee,
                    "retention_credit": retention_credit, "discarded_precedent": discarded_precedent,
                    "retained_precedent": retained_precedent}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary="Added the fee ledger and the distinguished/retained precedents",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "billed", "precedent"]},
            refs=[annual_fee["ledger_id"], retention_credit["ledger_id"],
                  discarded_precedent["precedent_id"], retained_precedent["precedent_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "retrieval_decision_seq": decision.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        posted = evidence["annual_fee"]["posted_date"]
        window_end = (date.fromisoformat(posted) + timedelta(days=30)).isoformat()
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="annual_fee_refund_window"),
            type=EventType.COMPUTATION,
            summary=f"Annual fee posted {posted}; the 30-calendar-day refund window ends {window_end}",
            payload={"helper": "calendar_days_window", "inputs": {"posted_date": posted, "window_days": 30},
                     "output": window_end, "runtime": "registered_python_helper"},
            refs=[evidence["annual_fee"]["ledger_id"]],
        )
        interaction_id = state["interaction_ids"][0]
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.FINDING_UPDATED,
            summary="Two explicit cancellation requests were never processed; a numeric credit-score-drop "
                    "prediction was used to talk the customer out of closing",
            payload={"finding_ids": ["F1", "F2"], "status": "substantiated_candidate",
                     "cancellation_requests": 2, "cancellation_processed": False,
                     "numeric_score_drop_points": 100,
                     "retention_credit_amount": evidence["retention_credit"]["amount"],
                     "af_refund_window_end": window_end},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02",
                  f"{interaction_id}:t03", f"{interaction_id}:t04"],
        )
        return {"af_refund_window": window_end, "computation_seq": computation.seq,
                "reconcile_event_seq": finding.seq, "root_cause_changed": False}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        checks = {
            "first_cancellation_request_exact": "i want to close the card" in turns["t01"]["text"].lower(),
            "numeric_score_drop_exact": "your credit score will drop like a hundred points" in turns["t02"]["text"].lower(),
            "second_cancellation_request_exact": "i still want to close it" in turns["t03"]["text"].lower(),
            "closure_deflected_not_processed": (
                "call us back" in turns["t04"]["text"].lower() and "apply the credit" in turns["t04"]["text"].lower()
            ),
            "annual_fee_amount_matches": evidence["annual_fee"]["amount"] == "450.00",
            "retention_credit_amount_matches": evidence["retention_credit"]["amount"] == "-200.00",
            "af_refund_window_correct": state["af_refund_window"] == "2026-11-29",
            "pre0017_distinguished": (
                evidence["discarded_precedent"]["precedent_id"] == "PRE-0017"
                and "utilization" in evidence["discarded_precedent"]["body"].lower()
            ),
            "pre0016_retained": (
                evidence["retained_precedent"]["precedent_id"] == "PRE-0016"
                and "MC-06" in evidence["retained_precedent"]["categories"]
            ),
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact numeric credit-score-drop sentence",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t02",
                     "quote": turns["t02"]["text"], "substring_match": checks["numeric_score_drop_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C17_L3", "result": "pass" if passed else "fail"},
                refs=[evidence["annual_fee"]["ledger_id"], evidence["discarded_precedent"]["precedent_id"],
                      evidence["retained_precedent"]["precedent_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C17 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[evidence["retained_precedent"]["precedent_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "severity is medium, not high, so the panel threshold is not met despite the $450 "
                                 "remediation; no systemic or protected-situation trigger is present",
                "panel_event_seqs": [], "outreach_needed": True}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        latest_date = latest_safe_decision(interaction["started_at_utc"], interaction["started_at_utc"], 10)
        respond_by = f"{latest_date}T23:59:59Z"
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION,
            summary=f"Computed monitoring deadline {latest_date}, well inside the {state['af_refund_window']} "
                    "annual-fee refund window",
            payload={"helper": "latest_safe_decision", "inputs": {
                "interaction_date": interaction["started_at_utc"][:10],
                "trigger_date": interaction["started_at_utc"][:10], "business_days": 10,
                "excluded_holiday": "2026-11-11"},
                "output": latest_date, "af_refund_window_end": state["af_refund_window"],
                "runtime": "registered_python_helper"},
            refs=[interaction["interaction_id"]],
        )
        request, used = self.tools.execute(
            "message_customer", {
                "customer_id": interaction["customer_id"],
                "question": "You asked twice to close your card, but instead we applied a $200 statement credit "
                             "and did not process the closure. Do you still want the card closed now?",
                "respond_by": respond_by, "idempotency_key": f"{state['review_id']}:OUTREACH",
            }, rationale="Confirm with the customer whether to honor the cancellation before deciding remediation",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used,
                "latest_safe_decision": respond_by, "deadline_event_seq": computation.seq,
                "resume_target": "decide"}

    def prepare_wait(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["artifact_request"]
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Recorded the customer-outreach wait and latest safe decision",
            payload={"path": "deadlines.json", "expected_at": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "af_refund_window_end": state["af_refund_window"],
                     "artifact_id": request["artifact_id"]}, refs=[request["artifact_id"]],
        )
        wait = self.ledger.emit(
            **node_context(state), actor=Actor(kind="harness", name="virtual_clock"),
            type=EventType.WAIT_SUSPENDED, summary="Suspended only for the customer's outreach reply",
            payload={"artifact_id": request["artifact_id"], "until": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "idempotency_key": request["idempotency_key"]}, refs=[request["artifact_id"]],
        )
        return {"status": "suspended", "termination": "waiting_external",
                "wait_event_seqs": [update.seq, wait.seq]}

    def ingest_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        resumed = state["resume_payload"]
        now = datetime.fromisoformat(resumed["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)
        if not resumed["arrived"] or resumed["artifact"] is None:
            raise RuntimeError("C17 customer reply did not arrive before latest safe decision")
        arrived = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.PERSONA_REPLY,
            summary="Released the customer's outreach reply into the agent view",
            payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                     "available_at": resumed["virtual_now"],
                     "reply_blob": self.ledger.put_blob(resumed["artifact"])},
            refs=[resumed["artifact_id"], state["interaction_ids"][0]],
        )
        wait = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
            summary="Resumed C17 after the customer's reply arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "customer_reply_arrived"}, refs=[resumed["artifact_id"]],
        )
        evidence = {**state["evidence"], "customer_reply": resumed["artifact"]["text"]}
        return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "artifact_event_seqs": [arrived.seq, wait.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        reply = state["evidence"]["customer_reply"]
        confirmed_close = "close" in reply.lower()
        interaction_id = state["interaction_ids"][0]
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-05 and MC-06 substantiated against the colleague; the customer confirmed the closure",
            payload={"findings": [
                {"finding_id": "F1", "category": "MC-05", "status": "substantiated", "attributable_to": "colleague"},
                {"finding_id": "F2", "category": "MC-06", "status": "substantiated", "attributable_to": "colleague"},
            ], "customer_reply": reply, "confirmed_close": confirmed_close},
            refs=[f"{interaction_id}:t02", f"{interaction_id}:t04"],
        )
        if not confirmed_close:
            raise RuntimeError("C17 customer reply did not confirm the closure")
        return {"finding_event_seq": event.seq, "confirmed_close": confirmed_close}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for a single-interaction colleague finding",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "case-local finding from one verified interaction; no generalizable pattern basis",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        annual_fee = evidence["annual_fee"]
        retention_credit = evidence["retention_credit"]
        discarded = evidence["discarded_precedent"]
        retained = evidence["retained_precedent"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", f"{interaction_id}:t03",
                       f"{interaction_id}:t04", annual_fee["ledger_id"], retention_credit["ledger_id"],
                       discarded["precedent_id"], retained["precedent_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["retrieval_decision_seq"], state["computation_seq"],
            state["reconcile_event_seq"], state["deadline_event_seq"], state["finding_event_seq"],
            state["memory_event_seq"], *state["integrity_event_seqs"], *state["verification_seqs"],
            *state["wait_event_seqs"], *state["artifact_event_seqs"],
        ]))
        findings = [
            Finding(
                finding_id="F1", category="MC-05", status="substantiated", attributable_to="colleague",
                severity="medium", interaction_id=interaction_id,
                evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t02",
                                 "start_s": float(turns["t02"]["start_s"]), "end_s": float(turns["t02"]["end_s"]),
                                 "quote": turns["t02"]["text"], "verified": True}],
                structured_evidence=[
                    {"source": "precedents", "id": discarded["precedent_id"],
                     "fact": "distinguished: a general utilization/length-of-history caution was held no_error; a "
                             "specific hundred-point prediction is not something anyone can accurately predict"},
                ], policy_refs=[], confidence=state["computed_confidence"],
            ),
            Finding(
                finding_id="F2", category="MC-06", status="substantiated", attributable_to="colleague",
                severity="medium", interaction_id=interaction_id,
                evidence_spans=[
                    {"interaction_id": interaction_id, "turn_id": "t01",
                     "start_s": float(turns["t01"]["start_s"]), "end_s": float(turns["t01"]["end_s"]),
                     "quote": turns["t01"]["text"], "verified": True},
                    {"interaction_id": interaction_id, "turn_id": "t03",
                     "start_s": float(turns["t03"]["start_s"]), "end_s": float(turns["t03"]["end_s"]),
                     "quote": turns["t03"]["text"], "verified": True},
                    {"interaction_id": interaction_id, "turn_id": "t04",
                     "start_s": float(turns["t04"]["start_s"]), "end_s": float(turns["t04"]["end_s"]),
                     "quote": turns["t04"]["text"], "verified": True},
                ],
                structured_evidence=[
                    {"source": "fee_ledger", "id": retention_credit["ledger_id"],
                     "fact": f"an unrequested {retention_credit['amount']} retention credit was applied instead of "
                             "honoring either cancellation request"},
                    {"source": "precedents", "id": retained["precedent_id"],
                     "fact": "retained as the controlling MC-06 precedent (the catalog cites PRE-0044, which does "
                             "not exist in this dataset; PRE-0016 is used instead)"},
                ], policy_refs=[], confidence=state["computed_confidence"],
            ),
        ]
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"],
            "findings": [finding.model_dump() for finding in findings],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "honor_cancellation_request"},
                {"action": "refund_annual_fee", "amount": annual_fee["amount"]},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the colleague had actually processed the cancellation request instead "
                                          "of applying an unrequested retention credit"},
            "waits": [{"artifact_id": state["artifact_request"]["artifact_id"], "kind": "customer_reply",
                       "requested_at": state["artifact_request"]["requested_at"],
                       "expected_at": state["artifact_request"]["expected_at"],
                       "arrived_at": state["virtual_now"], "latest_safe_decision": state["latest_safe_decision"],
                       "result": "arrived"}],
            "memory_ops": [{"op": "skip",
                            "reason": "case-local finding from one verified interaction; no generalizable pattern",
                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "the credit-score comment was a permissible general caution covered by PRE-0017",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "a specific hundred-point prediction is unverifiable misinformation, "
                                       "distinct from PRE-0017's general caution",
                 "status": "supported", "evidence_for": source_refs},
                {"id": "H3", "label": "the colleague eventually processed one of the two cancellation requests",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H4", "label": "neither explicit cancellation request was ever processed; an unrequested "
                                       "retention credit was applied instead, per PRE-0016",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [
                {"doc_id": discarded["precedent_id"],
                 "why": "distinguished: general utilization/length-of-history caution, no numeric prediction"},
                {"doc_id": retained["precedent_id"],
                 "why": "retained: cancellation not processed, MC-06 substantiated (substituted for the catalog's "
                        "non-existent PRE-0044)"},
            ],
            "summary_for_record": (
                "MC-05 and MC-06 substantiated against the colleague. The colleague predicted a specific "
                "hundred-point credit-score drop to talk the customer out of closing the card, then applied an "
                f"unrequested {retention_credit['amount']} retention credit and deflected both explicit "
                "cancellation requests with 'call us back' instead of processing them. The customer confirmed by "
                "outreach reply that the card should still be closed, within both the monitoring deadline and the "
                f"annual-fee refund window ending {state['af_refund_window']}; the ${annual_fee['amount']} annual "
                "fee is refunded and the $200 retention credit is not clawed back."
            ),
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C17 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
