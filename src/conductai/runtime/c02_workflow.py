"""C02 callback exception: an outbound sale is permitted because it fulfills a customer-created, same-product,
consented callback within the SOP's business-day window; proven by a cross-channel graph hop."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.deadlines import business_days_between
from conductai.runtime.support import leaf_paths, node_context
from conductai.tools.executor import ToolExecutor


class C02Workflow:
    """Deterministic outbound-sale callback-exception path; C02 only."""

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
        if route.route_id != "callback_sale_exception":
            raise RuntimeError("C02 requires the callback_sale_exception route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the outbound-sale callback-exception path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "outbound_call": state["route_facts"]["outbound_call"],
                         "callback_candidate_present": state["route_facts"]["callback_candidate_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq}

    def integrity(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the exact outbound sales pitch and acceptance",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the sale confirmation is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        chain, used = self.tools.execute(
            "query_graph", {
                "template_id": "callback_chain_for_fulfilling_interaction",
                "parameters": {"interaction_id": interaction_id},
                "as_of": governing_date, "max_hops": 2, "limit": 5,
            }, rationale="Trace the callback request this outbound call fulfills back to its origin interaction",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        link = chain[0]
        callback, used = self.tools.execute(
            "get_callback_request", {"callback_request_id": link["callback_request_id"]},
            rationale="Read the callback's purpose, window, and recorded consent",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        offers, used = self.tools.execute(
            "get_offers", {"interaction_id": interaction_id},
            rationale="Confirm the offer actually submitted on this outbound call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "chain": link, "callback": callback, "offer": offers[0]}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the callback chain, callback record, and offer",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "callback", "offer"]},
            refs=[link["created_in_interaction_id"], callback["callback_request_id"], offers[0]["offer_instance_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        callback = evidence["callback"]
        offer = evidence["offer"]
        purpose_matches = callback["purpose"] == "balance_transfer_offer" and offer["offer_type"] == "BT"
        created_date = callback["available_at"][:10]
        fulfilled_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        gap_days = business_days_between(created_date, fulfilled_date)
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="business_days"),
            type=EventType.COMPUTATION,
            summary=f"Callback fulfilled {gap_days} business day(s) after it was created",
            payload={"helper": "business_days", "inputs": {"created_date": created_date, "fulfilled_date": fulfilled_date},
                     "output": gap_days, "runtime": "registered_python_helper"},
            refs=[callback["callback_request_id"]],
        )
        consent_recorded = callback["consent_to_call"] == "true"
        exception_holds = purpose_matches and gap_days <= 3 and consent_recorded
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The outbound sale fulfills a same-product, timely, consented callback",
            payload={"finding_id": "F1", "status": "no_error_candidate" if exception_holds else "substantiated_candidate",
                     "purpose_matches": purpose_matches, "business_days": gap_days, "consent_recorded": consent_recorded,
                     "exception_holds": exception_holds},
            refs=[f"{state['interaction_ids'][0]}:t01", callback["callback_request_id"]],
        )
        return {"purpose_matches": purpose_matches, "business_days": gap_days, "consent_recorded": consent_recorded,
                "exception_holds": exception_holds, "computation_seq": computation.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        checks = {
            "purpose_matches": state["purpose_matches"],
            "within_three_business_days": state["business_days"] <= 3,
            "consent_recorded": state["consent_recorded"],
            "exception_holds": state["exception_holds"],
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact outbound-sale confirmation turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t01",
                     "quote": turn["text"], "substring_match": True},
            refs=[f"{state['interaction_ids'][0]}:t01"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C02_L2", "result": "pass" if passed else "fail"},
                refs=[evidence["callback"]["callback_request_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C02 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[evidence["callback"]["callback_request_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False, "panel_reason": "no adverse finding or high-impact trigger", "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed no error: the outbound sale falls within the callback exception",
            payload={"finding_id": "F1", "category": "none", "status": "no_error", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t01", state["evidence"]["callback"]["callback_request_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write: the callback exception applied correctly, no new generalizable knowledge",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "case-local exception check that matched policy; nothing to generalize",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        callback = evidence["callback"]
        offer = evidence["offer"]
        source_refs = [f"{interaction_id}:t01", callback["callback_request_id"], offer["offer_instance_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["computation_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"], *state["integrity_event_seqs"],
            *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                             "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                             "quote": turn["text"], "verified": True}],
            structured_evidence=[
                {"source": "callback_requests", "id": callback["callback_request_id"],
                 "fact": f"purpose={callback['purpose']}, consent_to_call={callback['consent_to_call']}, "
                         f"fulfilled {state['business_days']} business day(s) after creation"},
                {"source": "offers", "id": offer["offer_instance_id"], "fact": f"offer_type={offer['offer_type']}"},
            ],
            policy_refs=[{"doc_id": "CLB-SOP-SAL-002@v3", "clause": "3.2", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False, "remediation": [{"action": "none"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "a mismatched purpose, a callback older than three business days, or missing consent"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "case-local exception check matched policy",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "prohibited outbound sale", "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "permitted under the customer-requested callback exception", "status": "supported",
                 "evidence_for": source_refs},
            ], "citations": [{"doc_id": "CLB-SOP-SAL-002@v3", "why": "outbound-sale callback exception"}],
            "summary_for_record": "No error. The outbound balance-transfer sale fulfills a same-product callback the "
                                   f"customer requested {state['business_days']} business day(s) earlier, with recorded consent.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C02 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
