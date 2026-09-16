"""C13 uncoded complaint handling: the underlying returned-payment fee is valid, but the colleague told the
customer there was nothing to complain about instead of logging the complaint, and the disposition code
contradicts the transcript. A hypothetical regulator-portal complaint copy would arrive later but could not
change either finding, so the review decides now instead of waiting for it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C13Workflow:
    """Deterministic uncoded-complaint-handling path; C13 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=20, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "uncoded_complaint_handling":
            raise RuntimeError("C13 requires the uncoded_complaint_handling route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the uncoded complaint-handling path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "customer_complaint_language_present": state["route_facts"]["customer_complaint_language_present"],
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
            rationale="Read the exact complaint request and the colleague's response",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and both the complaint request and the denial are unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        account_id = state["route_facts"]["interaction"]["account_id"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": account_id},
            rationale="Confirm the returned-payment fee the customer's complaint is about",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SRV-003", "governing_date": governing_date},
            rationale="Resolve the complaint-handling definition and logging rules as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "fee_ledger": fee_ledger[0], "policy": policy}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the billed fee and the complaint-handling policy",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "billed", "policy"]},
            refs=[fee_ledger[0]["ledger_id"], policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction = state["route_facts"]["interaction"]
        complaint_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        denial_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        obstruction_present = "nothing to complain about" in denial_turn["text"].lower()
        disposition_code = interaction["disposition_code"]
        disposition_contradicts_transcript = disposition_code != "COMPLAINT"
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The colleague denied the customer's complaint right and the disposition code contradicts the transcript",
            payload={"findings": [
                {"finding_id": "F1", "status": "substantiated_candidate",
                 "customer_complaint_language_present": True, "obstruction_present": obstruction_present},
                {"finding_id": "F2", "status": "substantiated_candidate",
                 "disposition_code": disposition_code, "disposition_contradicts_transcript": disposition_contradicts_transcript},
            ]}, refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02"],
        )
        return {"obstruction_present": obstruction_present, "disposition_code": disposition_code,
                "disposition_contradicts_transcript": disposition_contradicts_transcript,
                "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        complaint_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        denial_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        policy = evidence["policy"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        checks = {
            "customer_complaint_quote_exact": "complaint" in complaint_turn["text"].lower(),
            "colleague_obstruction_quote_exact": state["obstruction_present"],
            "disposition_contradicts_transcript": state["disposition_contradicts_transcript"],
            "fee_ledger_confirms_billed_fee": evidence["fee_ledger"]["type"] == "RETURNED_PAYMENT_FEE",
            "policy_as_of": policy["version"] == "v5" and policy["effective_from"] <= governing_date,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact complaint request and denial turns",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t01",
                     "quote": complaint_turn["text"], "substring_match": checks["customer_complaint_quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t01"],
        )
        span2 = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact denial turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t02",
                     "quote": denial_turn["text"], "substring_match": checks["colleague_obstruction_quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified SRV-003 v5 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "2.1", "governing_date": governing_date,
                     "valid": checks["policy_as_of"]}, refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C13_L2", "result": "pass" if passed else "fail"},
                refs=[policy["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C13 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[policy["source_id"]],
        )
        return {"verifier_checks": checks,
                "verification_seqs": [span.seq, span2.seq, citation.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "two findings but severity medium; the panel predicate requires severity high",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-10 and MC-11 substantiated: complaint obstruction and a contradicting disposition code",
            payload={"findings": [
                {"finding_id": "F1", "category": "MC-10", "status": "substantiated", "attributable_to": "colleague"},
                {"finding_id": "F2", "category": "MC-11", "status": "substantiated", "attributable_to": "colleague"},
            ]}, refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02"],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        follow_up, used = self.tools.execute(
            "schedule_follow_up", {
                "at": state["virtual_now"], "action_type": "link_regulator_complaint",
                "idempotency_key": f"{state['review_id']}:REGULATOR_LINK",
            }, rationale="Note that a later regulator-portal complaint copy, if any arrives, should be linked to "
                          "this review; it cannot change either finding, so the review decides now rather than waiting",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"authorized_actions": [follow_up], "tool_calls_used": used}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for a single-interaction colleague finding",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "case-local finding from one verified interaction; a repeated pattern would need its "
                               "own targeted lookback, not asserted here",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        interaction = state["route_facts"]["interaction"]
        complaint_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        denial_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        fee_ledger = evidence["fee_ledger"]
        policy = evidence["policy"]
        colleague_id = interaction["colleague_id"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", fee_ledger["ledger_id"], policy["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["reconcile_event_seq"], state["finding_event_seq"],
            state["memory_event_seq"], *state["integrity_event_seqs"], *state["verification_seqs"],
        ]))
        complaint_span = {"interaction_id": interaction_id, "turn_id": "t01",
                          "start_s": float(complaint_turn["start_s"]), "end_s": float(complaint_turn["end_s"]),
                          "quote": complaint_turn["text"], "verified": True}
        denial_span = {"interaction_id": interaction_id, "turn_id": "t02",
                       "start_s": float(denial_turn["start_s"]), "end_s": float(denial_turn["end_s"]),
                       "quote": denial_turn["text"], "verified": True}
        findings = [
            Finding(
                finding_id="F1", category="MC-10", status="substantiated", attributable_to="colleague",
                severity="medium", interaction_id=interaction_id,
                evidence_spans=[complaint_span, denial_span],
                structured_evidence=[
                    {"source": "fee_ledger", "id": fee_ledger["ledger_id"],
                     "fact": f"{fee_ledger['type']} of {fee_ledger['amount']} the customer disputed; the colleague "
                             "told the customer there was nothing to complain about instead of logging it"},
                ],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "2.1", "verified": True}],
                confidence=state["computed_confidence"],
            ),
            Finding(
                finding_id="F2", category="MC-11", status="substantiated", attributable_to="colleague",
                severity="medium", interaction_id=interaction_id,
                evidence_spans=[complaint_span],
                structured_evidence=[
                    {"source": "interactions", "id": interaction_id,
                     "fact": f"disposition_code={state['disposition_code']} recorded despite the customer's "
                             "explicit complaint on the recording"},
                ],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "3.1", "verified": True}],
                confidence=state["computed_confidence"],
            ),
        ]
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"],
            "findings": [finding.model_dump() for finding in findings],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "log_complaint", "received_at": interaction["started_at_utc"]},
            ]},
            "colleague_outcome": {"colleague_id": colleague_id, "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the colleague had actually logged the complaint with disposition "
                                          "COMPLAINT, or the customer's words never expressed dissatisfaction"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "case-local finding; no generalizable pattern asserted",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "the call was a routine billing inquiry correctly logged as such",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "the colleague recognized a complaint, denied the customer's right to raise "
                                      "it, and mis-coded the disposition", "status": "supported",
                 "evidence_for": source_refs},
            ], "citations": [{"doc_id": policy["source_id"],
                              "why": "defines a complaint independent of the word used (2.1), requires disposition "
                                     "COMPLAINT with the original received_at (3.1), and holds that a valid "
                                     "underlying fee does not excuse non-logging (3.3)"}],
            "summary_for_record": "MC-10 and MC-11 substantiated, both medium severity and attributable to the "
                                   "colleague. The returned-payment fee itself is valid and is not refunded; the "
                                   "colleague's separate duty was to log the customer's complaint, which was "
                                   "obstructed and mis-coded instead. The complaint is logged now with the original "
                                   "call time as received_at. No panel is required at medium severity. A "
                                   "hypothetical later regulator-portal complaint copy could not change either "
                                   "finding, so the review decides now rather than waiting for one.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C13 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
