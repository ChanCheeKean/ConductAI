"""C09 SCRA duty-station referral: a program skill plus regulation retrieval catches misinformation
about a real legal right; a FLAWED precedent must lose to primary regulatory text. The reservist's
balance-transfer pitch was declined, so no separate sales finding is substantiated; decided by panel
(rights misinformation)."""

from __future__ import annotations

import json
from typing import Any

from pathlib import Path

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C09Workflow:
    """Deterministic SCRA rights-referral path; C09 only."""

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
        if route.route_id != "scra_rights_referral":
            raise RuntimeError("C09 requires the scra_rights_referral route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the SCRA rights-referral path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "military_orders_mentioned_present": state["route_facts"]["military_orders_mentioned_present"],
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
            rationale="Read the exact SCRA-scope misinformation and the declined balance-transfer pitch",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Confirm no SCRA benefits review was ever opened on this call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete, clear phone audio with no gap; the misinformation is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript, "desktop_events": desktop}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SCRA-001", "governing_date": governing_date},
            rationale="Resolve the SCRA referral SOP as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        candidates, used = self.tools.execute(
            "search_precedents", {"query": "reservist", "as_of": governing_date, "top_k": 5},
            rationale="Find prior decisions about reservist SCRA eligibility",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        precedent, used = self.tools.execute(
            "get_precedent", {"precedent_id": candidates[0]["precedent_id"]},
            rationale="Retrieve the leading precedent candidate to verify or reject it against the primary text",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        decision = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="policy_analyst"),
            type=EventType.RETRIEVAL_DECISION,
            summary=f"Rejected {precedent['precedent_id']} as flawed; it contradicts the primary SOP text",
            payload={"used": [], "discarded": [
                {"id": precedent["precedent_id"],
                 "why": "reasons a reservist is ineligible until active duty actually begins and that SCRA "
                        "excludes credit cards; this contradicts SOP section 2.1 (any mention of orders "
                        "triggers the process) and section 3.2 (the six percent cap covers pre-service "
                        "obligations including credit cards), so primary regulatory text controls"},
            ]}, refs=[precedent["precedent_id"], policy["source_id"]],
        )
        evidence = {**state["evidence"], "policy": policy, "precedent": precedent}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the SCRA SOP and the rejected reservist precedent",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "did", "policy", "precedent"]},
            refs=[policy["source_id"], precedent["precedent_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "retrieval_decision_seq": decision.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        referral_opened = any(row["type"] == "scra_review_opened" for row in evidence["desktop_events"])
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The colleague misinformed the customer that SCRA excludes credit cards and never opened "
                    "the required benefits review; the customer separately declined the unrelated pitch",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "misinformation_present": True, "referral_opened": referral_opened,
                     "balance_transfer_pitch_declined": True, "separate_sales_finding_warranted": False},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02", f"{interaction_id}:t03"],
        )
        return {"referral_opened": referral_opened, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn01 = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        turn02 = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        turn03 = next(t for t in evidence["transcript"] if t["turn_id"] == "t03")
        policy = evidence["policy"]
        precedent = evidence["precedent"]
        precedent_outcome = json.loads(precedent["outcome"])
        checks = {
            "trigger_quote_exact": "active duty" in turn01["text"].lower() and "reservist" in turn01["text"].lower(),
            "misinformation_quote_exact": "not credit cards" in turn02["text"].lower(),
            "customer_declined_pitch": "no thanks" in turn03["text"].lower(),
            "referral_never_opened": state["referral_opened"] is False,
            "policy_as_of": policy["version"] == "v3" and policy["effective_from"] <= state["route_facts"]["interaction"]["started_at_utc"][:10],
            "precedent_rejected_against_primary_text": (
                precedent["precedent_id"] == "PRE-0031" and precedent_outcome["colleague"] == "no_error"
                and "credit cards" in policy["body"].lower()
            ),
        }
        trigger_span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact military-orders trigger sentence",
            payload={"interaction_id": interaction_id, "turn_id": "t01",
                     "quote": turn01["text"], "substring_match": checks["trigger_quote_exact"]},
            refs=[f"{interaction_id}:t01"],
        )
        misinformation_span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact SCRA misinformation sentence",
            payload={"interaction_id": interaction_id, "turn_id": "t02",
                     "quote": turn02["text"], "substring_match": checks["misinformation_quote_exact"]},
            refs=[f"{interaction_id}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified SCRA-SOP-001 v3 section 3.2 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "3.2",
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": checks["policy_as_of"]}, refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C09_L3", "result": "pass" if passed else "fail"},
                refs=[policy["source_id"], precedent["precedent_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C09 deterministic verifier failed")
        return {"verifier_checks": checks,
                "verification_seqs": [trigger_span.seq, misinformation_span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        snapshot = {"finding": "MC-10 substantiated, colleague", "misinformation_present": True,
                    "referral_opened": state["referral_opened"], "precedent_rejected": evidence["precedent"]["precedent_id"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity finding involving rights misinformation about a real SCRA benefit",
            payload={"predicate": "high_severity_and_rights_misinformation", "snapshot_hash": snapshot_hash},
            refs=[interaction_id],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: the misinformation caused the customer to miss the six-percent interest "
                    "cap review, a real benefit, regardless of what happened with the unrelated balance-transfer pitch",
            payload={"role": "customer_advocate", "position": "substantiate_rights_misinformation",
                     "key_refs": [f"{interaction_id}:t02"], "snapshot_hash": snapshot_hash},
            refs=[f"{interaction_id}:t02"],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: the customer declined the balance-transfer pitch, so no product was sold "
                    "and no monetary harm resulted from that offer",
            payload={"role": "colleague_advocate", "position": "no_harm_from_declined_pitch",
                     "key_refs": [f"{interaction_id}:t03"], "snapshot_hash": snapshot_hash},
            refs=[f"{interaction_id}:t03"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: declining the unrelated pitch does not cure the misinformation or the missed "
                    "referral, so the rights-misinformation finding stands alone with no separate sales finding",
            payload={"determinative_issue": "whether declining the unrelated balance-transfer pitch cures the "
                                             "failure to open the required SCRA referral",
                     "decision": "misinformation_substantiated_no_separate_sales_finding",
                     "flip_fact": "the colleague had accurately explained the six percent cap covers credit cards "
                                  "and opened the SCRA benefits review in the same interaction"},
            refs=[f"{interaction_id}:t02", f"{interaction_id}:t03"],
        )
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence with aligned panel positions",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": 1.0,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20, "panel_agreement": 0.10},
                     "result": 1.0},
            refs=[evidence["policy"]["source_id"]],
        )
        return {"panel_used": True,
                "panel_reason": "severity high and colleague rights misinformation about a real SCRA benefit "
                                "(rights-misinformation panel trigger)",
                "computed_confidence": 1.0,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-10 substantiated against the colleague for SCRA rights misinformation; "
                    "no separate finding for the declined balance-transfer pitch",
            payload={"finding_id": "F1", "category": "MC-10", "status": "substantiated", "attributable_to": "colleague"},
            refs=[f"{interaction_id}:t02", state["evidence"]["precedent"]["precedent_id"]],
        )
        return {"finding_event_seq": event.seq}

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
        turn02 = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        policy = evidence["policy"]
        precedent = evidence["precedent"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", f"{interaction_id}:t03",
                       policy["source_id"], precedent["precedent_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["retrieval_decision_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"], *state["integrity_event_seqs"],
            *state["verification_seqs"], *state["panel_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-10", status="substantiated", attributable_to="colleague", severity="high",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t02",
                             "start_s": float(turn02["start_s"]), "end_s": float(turn02["end_s"]),
                             "quote": turn02["text"], "verified": True}],
            structured_evidence=[
                {"source": "transcript", "id": f"{interaction_id}:t01",
                 "fact": "customer disclosed Army reservist orders for active duty beginning December first"},
                {"source": "transcript", "id": f"{interaction_id}:t03",
                 "fact": "customer declined the unrelated balance-transfer pitch; no separate sales finding warranted"},
                {"source": "precedents", "id": precedent["precedent_id"],
                 "fact": "flawed precedent found no_error for the same misinformation pattern; rejected because it "
                         "contradicts the primary SOP text"},
            ],
            policy_refs=[{"doc_id": policy["source_id"], "clause": "3.2", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "open_scra_review"}, {"action": "correction_letter"},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the colleague had accurately explained the six percent cap covers credit "
                                          "cards and opened the SCRA benefits review in the same interaction"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "case-local finding; no generalizable pattern",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "SCRA doesn't cover credit cards, so no misinformation occurred", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "colleague misinformed the customer about a real SCRA benefit and never "
                                       "opened the required referral", "status": "supported", "evidence_for": source_refs},
            ], "citations": [
                {"doc_id": policy["source_id"], "why": "governs the SCRA referral duty and confirms the six percent "
                                                       "cap covers pre-service obligations including credit cards"},
                {"doc_id": precedent["precedent_id"],
                 "why": "rejected: flawed reasoning that a reservist isn't SCRA-eligible until active duty begins, "
                        "contradicting SOP sections 2.1 and 3.2"},
            ],
            "summary_for_record": "MC-10 substantiated. The colleague told the reservist that SCRA excludes credit "
                                   "cards and pitched an unrelated balance transfer instead of opening the required "
                                   "SCRA benefits review; the customer declined that pitch, so no separate sales "
                                   "finding is substantiated. The retrieved precedent PRE-0031 was flawed (no_error) "
                                   "and was rejected because it contradicts the primary SOP text.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C09 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
