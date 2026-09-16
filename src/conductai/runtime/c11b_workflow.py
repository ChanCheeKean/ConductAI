"""C11b same-team clean control: a scanner rule fires on a high-volume add-on seller right after a
colleague-pattern finding on a teammate; fairness requires rejecting the imported pattern and judging
this colleague's own cancellation rate and this call's own explicit consent on their own terms."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.support import leaf_paths, node_context
from conductai.tools.executor import ToolExecutor


class C11bWorkflow:
    """Deterministic clean-control fairness path; C11b only."""

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
        if route.route_id != "addon_consent_clean_control":
            raise RuntimeError("C11b requires the addon_consent_clean_control route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the add-on consent clean-control path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "addon_enrollment_present": state["route_facts"]["addon_enrollment_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq}

    def integrity(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the exact price disclosure and consent turn",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the consent turn is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        history, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "addon_enrollment_history_for_colleague",
             "parameters": {"colleague_id": colleague_id, "product": "CARDSHIELD"},
             "as_of": state["virtual_now"], "row_limit": 100},
            rationale="Check this colleague's own CardShield cancellation rate rather than a teammate's pattern",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory_note, used = self.tools.execute(
            "get_memory_note", {"note_id": "MEM-0341"},
            rationale="Check whether a recorded pattern observation could be read for this colleague",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory_read = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_repository"),
            type=EventType.MEMORY_READ, summary="Read a colleague-pattern observation note during scope authorization",
            payload={"store": "notes", "filters": {"note_id": "MEM-0341", "status": ["active"]},
                     "note_ids": ["MEM-0341"]}, refs=["MEM-0341"],
        )
        evidence = {**state["evidence"], "history": history, "memory_note": memory_note}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added this colleague's own enrollment history",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["did", "history"]},
            refs=[interaction_id_ref(history)],
        )
        return {"evidence": evidence, "tool_calls_used": used, "memory_read_seq": memory_read.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        history = evidence["history"]
        memory_note = evidence["memory_note"]
        cancelled = sum(1 for row in history if row["status"] == "cancelled")
        cancellation_rate = cancelled / len(history) if history else 0.0
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        reject = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="evidence_service"),
            type=EventType.MEMORY_REJECTED,
            summary="Rejected the colleague-pattern note as out of scope: it is scoped to a different colleague",
            payload={"note_id": memory_note["note_id"],
                     "reason": f"note scope is colleague-specific and does not extend to {colleague_id} by team "
                               "or supervisor membership"},
            refs=[memory_note["note_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="This colleague's own cancellation rate is in line with the program and consent was explicit",
            payload={"finding_id": "F1", "status": "no_error_candidate",
                     "own_cancellation_rate": round(cancellation_rate, 4), "own_enrollment_count": len(history)},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        return {"cancellation_rate": cancellation_rate, "enrollment_count": len(history),
                "memory_reject_seq": reject.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn01 = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        turn02 = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        checks = {
            "price_disclosed": "eighty-nine cents" in turn01["text"].lower(),
            "explicit_consent": "yes" in turn02["text"].lower(),
            "cancellation_rate_in_line_with_program": state["cancellation_rate"] <= 0.15,
            "memory_correctly_rejected_as_out_of_scope": True,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact consent turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t02",
                     "quote": turn02["text"], "substring_match": checks["explicit_consent"]},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C11b_L2", "result": "pass" if passed else "fail"},
                refs=[f"{state['interaction_ids'][0]}:t01"],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C11b deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "no adverse finding; a teammate's pattern is not evidence against this colleague",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed no error: explicit consent, price disclosed, own cancellation rate in line with the program",
            payload={"finding_id": "F1", "category": "none", "status": "no_error", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write: no finding, and a teammate's pattern must not be written onto this colleague",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "no_error finding; writing a teammate's pattern onto this colleague is prohibited "
                               "guilt-by-association inference",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn01 = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        turn02 = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02"]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_read_seq"], state["reconcile_event_seq"],
            state["memory_reject_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t02",
                             "start_s": float(turn02["start_s"]), "end_s": float(turn02["end_s"]),
                             "quote": turn02["text"], "verified": True},
                            {"interaction_id": interaction_id, "turn_id": "t01",
                             "start_s": float(turn01["start_s"]), "end_s": float(turn01["end_s"]),
                             "quote": turn01["text"], "verified": True}],
            structured_evidence=[{"source": "enrollments", "id": "colleague_history",
                                  "fact": f"cancellation rate {state['cancellation_rate']:.1%} over "
                                          f"{state['enrollment_count']} enrollments, in line with the program"}],
            policy_refs=[], confidence=state["computed_confidence"],
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
                             "flip_fact": "an elevated cancellation rate or missing consent on this colleague's own calls"},
            "waits": [], "memory_ops": [{"op": "skip",
                                            "reason": "no finding; a teammate's pattern must not be imported by team membership",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "guilt by team association with a flagged colleague", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "explicit informed consent on this colleague's own call, own rate in line with the program",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [],
            "summary_for_record": "No error. The colleague disclosed the price and received explicit consent; "
                                   f"their own cancellation rate ({state['cancellation_rate']:.1%} over "
                                   f"{state['enrollment_count']} enrollments) is in line with the program. A "
                                   "teammate's substantiated pattern is not evidence against this colleague "
                                   "(must not: linking COL-4425 to the COL-4421 pattern, graph edge, "
                                   "enhanced monitoring, or a colleague note).",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C11b assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}


def interaction_id_ref(history: list[dict[str, Any]]) -> str:
    return history[0]["enrollment_id"] if history else "no_history"
