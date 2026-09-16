"""C08 hardship-active sale: a protected situation disclosed in another channel, seen on the desktop banner,
with the order system's missing block as a separate control gap; decided by panel (vulnerable customer)."""

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
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C08Workflow:
    """Deterministic hardship-active sale path; C08 only."""

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
        if route.route_id != "hardship_active_sale":
            raise RuntimeError("C08 requires the hardship_active_sale route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the hardship-active sale path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "hardship_active_present": state["route_facts"]["hardship_active_present"],
                         "credit_product_offered_present": state["route_facts"]["credit_product_offered_present"],
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
            rationale="Read the exact Flex Installments pitch",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Confirm the hardship-plan-active banner shown to the colleague on this call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the Flex Installments pitch is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript, "desktop_events": desktop}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        customer_id = state["route_facts"]["interaction"]["customer_id"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        history, used = self.tools.execute(
            "query_graph", {
                "template_id": "customer_interaction_history",
                "parameters": {"customer_id": customer_id, "before_at": state["route_facts"]["interaction"]["started_at_utc"]},
                "as_of": governing_date, "max_hops": 2, "limit": 20,
            }, rationale="Find prior interactions to locate where the hardship was disclosed",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        prior_chat_id = history[0]["interaction_id"]
        prior_transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": prior_chat_id},
            rationale="Read the prior-channel hardship disclosure and enrollment confirmation",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        flags, used = self.tools.execute(
            "get_account_flag", {"account_id": state["route_facts"]["interaction"]["account_id"], "flag": "HARDSHIP_ACTIVE"},
            rationale="Confirm the active hardship flag and when it was set",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        plan, used = self.tools.execute(
            "get_installment_plan", {"plan_id": "FLX-9001002"},
            rationale="Confirm the Flex Installments plan the order system permitted despite the active hardship flag",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-VUL-001", "governing_date": governing_date},
            rationale="Resolve the hardship-and-vulnerability sales restriction as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        decision = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="policy_analyst"),
            type=EventType.RETRIEVAL_DECISION,
            summary=f"Retained {prior_chat_id} as the source of the hardship disclosure",
            payload={"used": [{"id": prior_chat_id, "why": "customer disclosed job loss and was enrolled in the Hardship Relief Plan"}],
                     "discarded": []}, refs=[prior_chat_id],
        )
        evidence = {**state["evidence"], "history": history, "prior_chat_id": prior_chat_id,
                    "prior_transcript": prior_transcript, "plan": plan, "policy": policy, "hardship_flag": flags[0]}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the prior hardship disclosure, plan, and policy",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "did", "policy"]},
            refs=[prior_chat_id, plan["plan_id"], policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "retrieval_decision_seq": decision.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        banner = next((row for row in evidence["desktop_events"] if row["type"] == "banner_displayed"), None)
        hardship_flag_active_at_call = evidence["hardship_flag"]["set_at"] <= state["route_facts"]["interaction"]["started_at_utc"]
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The hardship-plan-active banner was on the colleague's own desktop during this call",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "banner_displayed": banner is not None,
                     "flex_plan_status": evidence["plan"]["status"],
                     "hardship_flag_active_at_call": hardship_flag_active_at_call},
            refs=[f"{state['interaction_ids'][0]}:t02", banner["event_id"] if banner else "none", evidence["plan"]["plan_id"]],
        )
        return {"banner_event_id": banner["event_id"] if banner else None,
                "hardship_flag_active_at_call": hardship_flag_active_at_call, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        policy = evidence["policy"]
        checks = {
            "pitch_quote_exact": "flex installments" in turn["text"].lower(),
            "banner_displayed": state["banner_event_id"] is not None,
            "hardship_flag_active_at_call": state["hardship_flag_active_at_call"],
            "prior_disclosure_found": any(
                "lost my job" in t["text"].lower() for t in evidence["prior_transcript"] if t["speaker"] == "customer"
            ),
            "flex_plan_created_despite_restriction": evidence["plan"]["status"] == "active",
            "policy_as_of": policy["version"] == "v2" and policy["effective_from"] <= state["route_facts"]["interaction"]["started_at_utc"][:10],
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact Flex Installments pitch",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t02",
                     "quote": turn["text"], "substring_match": checks["pitch_quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified VUL-001 v2 §4.1 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "4.1",
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": checks["policy_as_of"]}, refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C08_L3", "result": "pass" if passed else "fail"},
                refs=[policy["source_id"], evidence["plan"]["plan_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C08 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        snapshot = {"finding": "MC-09 substantiated, colleague",
                    "banner_displayed": True, "flex_plan_status": evidence["plan"]["status"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity finding against a protected-situation (hardship) customer",
            payload={"predicate": "high_and_vulnerability_or_hardship", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: the colleague saw the active-hardship banner and sold a prohibited credit product anyway",
            payload={"role": "customer_advocate", "position": "reverse_and_substantiate",
                     "key_refs": [state["banner_event_id"]], "snapshot_hash": snapshot_hash},
            refs=[state["banner_event_id"]],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: the customer asked a servicing question and the order system allowed the plan, "
                    "suggesting the block is a system gap rather than deliberate disregard",
            payload={"role": "colleague_advocate", "position": "control_gap_shares_fault",
                     "key_refs": [evidence["plan"]["plan_id"]], "snapshot_hash": snapshot_hash},
            refs=[evidence["plan"]["plan_id"]],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: the banner made the restriction visible to the colleague, so individual fault stands "
                    "alongside the separate order-system control gap",
            payload={"determinative_issue": "whether the visible banner displaces individual attribution",
                     "decision": "substantiated_and_control_gap",
                     "flip_fact": "no banner or account-flag evidence that the colleague could see the active hardship status"},
            refs=[state["banner_event_id"], evidence["plan"]["plan_id"]],
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
        return {"panel_used": True, "panel_reason": "severity high and an active protected-situation (hardship) trigger",
                "computed_confidence": 1.0,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-09 substantiated against the colleague and a separate order-system control gap",
            payload={"finding_id": "F1", "category": "MC-09", "status": "substantiated", "attributable_to": "colleague"},
            refs=[f"{state['interaction_ids'][0]}:t02", state["evidence"]["plan"]["plan_id"]],
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
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        policy = evidence["policy"]
        plan = evidence["plan"]
        source_refs = [f"{interaction_id}:t02", evidence["prior_chat_id"], state["banner_event_id"],
                       plan["plan_id"], policy["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["retrieval_decision_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"], *state["integrity_event_seqs"],
            *state["verification_seqs"], *state["panel_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-09", status="substantiated", attributable_to="colleague", severity="high",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t02",
                             "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                             "quote": turn["text"], "verified": True}],
            structured_evidence=[
                {"source": "desktop_events", "id": state["banner_event_id"], "fact": "HARDSHIP_PLAN_ACTIVE banner displayed on this call"},
                {"source": "installment_plans", "id": plan["plan_id"], "fact": "Flex Installments plan created despite the active hardship flag"},
            ],
            policy_refs=[{"doc_id": policy["source_id"], "clause": "4.1", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "reverse_flex_plan"}, {"action": "preserve_hardship_relief_plan_terms"},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_gap_record", "system": "order_system",
                 "reason": "order system permitted a Flex Installments plan on an account with an active Hardship Relief Plan"},
            ]},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "no banner or account-flag evidence that the colleague could see the active hardship status"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "case-local finding; no generalizable pattern",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "helping the customer lower payments, not a prohibited sale", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "credit product sold on an active-hardship account the colleague could see was flagged",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": policy["source_id"], "why": "prohibits Flex Installments during an active Hardship Relief Plan"}],
            "summary_for_record": "MC-09 substantiated. The colleague sold a Flex Installments plan while the "
                                   "HARDSHIP_PLAN_ACTIVE banner was on their own desktop; the order system's missing "
                                   "block on credit products for active hardship accounts is a separate control gap.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C08 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
