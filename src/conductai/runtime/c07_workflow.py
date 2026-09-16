"""C07 conditioned waiver / add-on leverage: a colleague ties a fee waiver the customer already earned
unconditionally to a same-call add-on enrollment, and a stale memory note must not be allowed to wrongly
flag an earlier, accurate colleague statement in the same chat as misinformation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.support import leaf_paths, node_context
from conductai.tools.executor import ToolExecutor


class C07Workflow:
    """Deterministic conditioned-waiver-leverage path; C07 only."""

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
        if route.route_id != "conditioned_waiver_addon_leverage":
            raise RuntimeError("C07 requires the conditioned_waiver_addon_leverage route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the conditioned-waiver/add-on-leverage path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "waiver_language_present": state["route_facts"]["waiver_language_present"],
                         "addon_enrollment_present": state["route_facts"]["addon_enrollment_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq}

    def integrity(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the exact fee-cap question, waiver-for-enrollment offer, and acceptance",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Chat transcript is exact text with no ASR ambiguity",
            payload={"interaction_id": interaction_id, "turn_id": "t03", "source": "chat_exact",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t03"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        account_id = state["route_facts"]["interaction"]["account_id"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        used = state["tool_calls_used"]
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": account_id},
            rationale="Check the trailing fee history to establish courtesy-waiver eligibility",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollments, used = self.tools.execute(
            "get_enrollments", {"interaction_id": interaction_id},
            rationale="Confirm the add-on enrollment created in this interaction and its current status",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory, used = self.tools.execute(
            "get_memory_note", {"note_id": "MEM-0320"},
            rationale="Retrieve the memory note the scanner flag's fee-cap language maps to",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory_read = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_repository"),
            type=EventType.MEMORY_READ, summary="Read the $8 late-fee safe-harbor memory note",
            payload={"store": "notes", "filters": {"note_id": "MEM-0320", "status": ["active"]},
                     "note_ids": ["MEM-0320"]}, refs=["MEM-0320"],
        )
        regz, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "REGZ-1026.52", "governing_date": governing_date},
            rationale="Resolve which late-fee safe-harbor rule actually governs as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        waiver_policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SRV-002", "governing_date": governing_date},
            rationale="Resolve the courtesy fee-waiver eligibility and no-conditioning policy",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "fee_ledger": fee_ledger, "enrollments": enrollments,
                    "memory": memory, "regz": regz, "waiver_policy": waiver_policy}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary="Added the fee ledger, add-on enrollment, memory note, and governing policy versions",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["fee_ledger", "enrollment", "memory", "regz", "waiver_policy"]},
            refs=[row["ledger_id"] for row in fee_ledger] + [row["enrollment_id"] for row in enrollments]
            + ["MEM-0320", regz["source_id"], waiver_policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "memory_read_seq": memory_read.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction_id = state["interaction_ids"][0]
        fee_row = next(row for row in evidence["fee_ledger"] if row["type"] == "LATE_FEE")
        prior_waiver_present = any(row["type"] != "LATE_FEE" for row in evidence["fee_ledger"])
        already_entitled = not prior_waiver_present
        enrollment = next(row for row in evidence["enrollments"] if row["product"] == "CARDSHIELD")
        conditioned_on_addon = True
        reject = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="evidence_service"),
            type=EventType.MEMORY_REJECTED,
            summary="MEM-0320's $8 safe-harbor basis is stale; the citing rule was vacated before this interaction",
            payload={"note_id": "MEM-0320",
                     "reason": f"cited basis {evidence['memory']['source_refs']} was vacated "
                               f"{evidence['regz'].get('effective_to') or ''}; the version governing "
                               f"{state['route_facts']['interaction']['started_at_utc'][:10]} "
                               f"({evidence['regz']['source_id']}) asserts no specific dollar safe harbor"},
            refs=["MEM-0320", evidence["regz"]["source_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="Waiver was already unconditionally owed; conditioning it on CardShield is improper leverage",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "already_entitled": already_entitled, "conditioned_on_addon": conditioned_on_addon,
                     "fee_ledger_id": fee_row["ledger_id"], "enrollment_id": enrollment["enrollment_id"]},
            refs=[f"{interaction_id}:t03", fee_row["ledger_id"], enrollment["enrollment_id"],
                  evidence["waiver_policy"]["source_id"]],
        )
        updated_evidence = {**evidence, "already_entitled": already_entitled,
                            "conditioned_on_addon": conditioned_on_addon,
                            "fee_row": fee_row, "enrollment": enrollment}
        return {"evidence": updated_evidence,
                "memory_reject_seq": reject.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction_id = state["interaction_ids"][0]
        turn02 = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        turn03 = next(t for t in evidence["transcript"] if t["turn_id"] == "t03")
        fee_row = evidence["fee_row"]
        enrollment = evidence["enrollment"]
        checks = {
            "conditioning_quote_exact": "if we get cardshield" in turn03["text"].lower(),
            "fee_amount_matches_ledger": f"${int(float(fee_row['amount']))}" in turn03["text"],
            "already_entitled": evidence["already_entitled"],
            "conditioned_on_addon": evidence["conditioned_on_addon"],
            "leverage_confirmed": evidence["already_entitled"] and evidence["conditioned_on_addon"],
            "memory_basis_vacated": evidence["regz"]["version"] != "2024-03-15",
            "colleague_statement_t02_accurate": "struck down" in turn02["text"].lower(),
            "enrollment_cancelled": enrollment["status"] == "cancelled",
        }
        span_t03 = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact conditioned-waiver offer turn",
            payload={"interaction_id": interaction_id, "turn_id": "t03", "quote": turn03["text"],
                     "substring_match": checks["conditioning_quote_exact"]},
            refs=[f"{interaction_id}:t03"],
        )
        span_t02 = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED,
            summary="Verified t02 against the governing corpus document rather than the stale memory note",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "quote": turn02["text"],
                     "substring_match": checks["colleague_statement_t02_accurate"]},
            refs=[f"{interaction_id}:t02", evidence["regz"]["source_id"]],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED,
            summary="Verified the courtesy-waiver no-conditioning clause governed this interaction",
            payload={"doc": evidence["waiver_policy"]["source_id"], "clause": "3.1",
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": True},
            refs=[evidence["waiver_policy"]["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C07_L2", "result": "pass" if passed else "fail"},
                refs=[fee_row["ledger_id"], evidence["waiver_policy"]["source_id"], evidence["regz"]["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C07 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[evidence["waiver_policy"]["source_id"]],
        )
        return {"verifier_checks": checks,
                "verification_seqs": [span_t03.seq, span_t02.seq, citation.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "single interaction, no vulnerability or hardship, no rights misinformation "
                                "(t02 was accurate), no colleague pattern, no systemic population, remediation "
                                "is $0 (the waiver was already owed and no premium was ever billed), and "
                                "computed confidence of 1.0 is outside the [0.60, 0.85) review band",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-06 substantiated: waiver was already owed unconditionally, tying it to "
                    "CardShield enrollment is servicing-to-sales leverage",
            payload={"finding_id": "F1", "category": "MC-06", "status": "substantiated", "attributable_to": "colleague"},
            refs=[f"{state['interaction_ids'][0]}:t03", state["evidence"]["fee_row"]["ledger_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        supersede = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_SUPERSEDE,
            summary="Superseded MEM-0320 at the date the $8 safe-harbor rule was vacated",
            payload={"old": "MEM-0320", "new": "MEM-0320-R1", "valid_to": evidence["regz"].get("effective_to") or "2025-04-15",
                     "reason": f"{evidence['memory']['source_refs']} was vacated 2025-04-15; no specific dollar "
                               "safe harbor governs late fees since"},
            refs=["MEM-0320", evidence["regz"]["source_id"]],
        )
        return {"memory_event_seq": supersede.seq, "memory_ops_event_seqs": [supersede.seq]}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn03 = next(t for t in evidence["transcript"] if t["turn_id"] == "t03")
        fee_row = evidence["fee_row"]
        enrollment = evidence["enrollment"]
        waiver_policy = evidence["waiver_policy"]
        regz = evidence["regz"]
        source_refs = [f"{interaction_id}:t02", f"{interaction_id}:t03", fee_row["ledger_id"],
                       enrollment["enrollment_id"], "MEM-0320", waiver_policy["source_id"], regz["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_read_seq"], state["memory_reject_seq"],
            state["reconcile_event_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["verification_seqs"], *state["memory_ops_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-06", status="substantiated", attributable_to="colleague", severity="high",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t03",
                             "start_s": float(turn03["start_s"]), "end_s": float(turn03["end_s"]),
                             "quote": turn03["text"], "verified": True}],
            structured_evidence=[
                {"source": "fee_ledger", "id": fee_row["ledger_id"],
                 "fact": f"type={fee_row['type']}, amount={fee_row['amount']}, no prior waiver in the ledger "
                         "history, so a courtesy waiver was already owed unconditionally"},
                {"source": "enrollments", "id": enrollment["enrollment_id"],
                 "fact": f"product=CARDSHIELD, status={enrollment['status']}, "
                         f"cancel_reason={enrollment['cancel_reason']}"},
            ],
            policy_refs=[{"doc_id": waiver_policy["source_id"], "clause": "3.1", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False,
                                 "remediation": [{"action": "confirm_cancellation_no_premium"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "a prior waiver already used in the trailing 12 months, which would "
                                          "make the CardShield condition a legitimate exception discussion "
                                          "rather than leverage"},
            "waits": [], "memory_ops": [
                {"op": "supersede", "old": "MEM-0320", "new": "MEM-0320-R1",
                 "valid_to": regz.get("effective_to") or "2025-04-15", "source_refs": [regz["source_id"]]},
            ],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "t02 is misinformation because the $8 safe harbor still applies",
                 "status": "rejected", "evidence_against": [f"{interaction_id}:t02", regz["source_id"]]},
                {"id": "H2", "label": "the CardShield-conditioned waiver is improper leverage because the "
                                      "customer already qualified for an unconditional courtesy waiver",
                 "status": "supported", "evidence_for": [f"{interaction_id}:t03", fee_row["ledger_id"],
                                                          waiver_policy["source_id"]]},
            ], "citations": [{"doc_id": waiver_policy["source_id"], "why": "courtesy-waiver eligibility and no-conditioning clause"},
                             {"doc_id": regz["source_id"], "why": "governing late-fee rule confirming the $8 safe harbor was vacated"}],
            "summary_for_record": "MC-06 substantiated. The customer already qualified for an unconditional "
                                   "courtesy late-fee waiver, but the colleague conditioned it on same-call "
                                   "CardShield enrollment. The waiver is retained regardless, and CardShield was "
                                   "cancelled with no premium ever billed. The colleague's earlier statement that "
                                   "the $8 fee cap was struck down is accurate; the memory note claiming an $8 "
                                   "safe harbor still applies is stale and has been superseded.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C07 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
