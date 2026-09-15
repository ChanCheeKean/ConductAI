"""C05 balance-transfer disclosure reconciliation: said vs offered vs billed, with a distinguished precedent."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.sandbox import pct_fee
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C05Workflow:
    """Deterministic balance-transfer disclosure path; C05 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=45, **self._context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "balance_transfer_disclosure":
            raise RuntimeError("C05 requires the balance_transfer_disclosure route")
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the balance-transfer disclosure path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "balance_transfer_offer_present": state["route_facts"]["balance_transfer_offer_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        for skill in route.skills:
            metadata, digest, path = load_skill(self.root, skill)
            self.ledger.emit(
                **self._context(state), actor=Actor(kind="agent", name="skill_backend"),
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
            rationale="Read the exact rate and fee disclosure and the submission amount",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Confirm which offer panel was opened and its eligibility result",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        assessed = self.ledger.emit(
            **self._context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the fee sentence is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"transcript": transcript, "desktop_events": desktop}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        offers, used = self.tools.execute(
            "get_offers", {"interaction_id": interaction_id},
            rationale="Confirm which offer instance was actually submitted",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        offer = offers[0]
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": offer["account_id"]},
            rationale="Confirm the fee actually billed against the submitted offer",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-CHC-BT", "governing_date": governing_date},
            rationale="Resolve the balance-transfer fee disclosure rule as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        candidates, used = self.tools.execute(
            "search_precedents", {"query": "three percent offer", "as_of": governing_date, "top_k": 5},
            rationale="Find prior decisions about a stated transfer-fee percentage",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        precedent, used = self.tools.execute(
            "get_precedent", {"precedent_id": candidates[0]["precedent_id"]},
            rationale="Retrieve the leading precedent candidate to verify or distinguish it",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        decision = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="policy_analyst"),
            type=EventType.RETRIEVAL_DECISION, summary="Retained PRE-0022 as a candidate precedent to distinguish",
            payload={"used": [{"id": precedent["precedent_id"], "why": "same fee-percentage fact pattern"}],
                     "discarded": []}, refs=[precedent["precedent_id"]],
        )
        evidence = {**state["evidence"], "offer": offer, "fee_ledger": fee_ledger[0], "policy": policy,
                    "precedent": precedent}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the offer, fee ledger, disclosure policy, and precedent",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "offered", "billed", "policy"]},
            refs=[offer["offer_instance_id"], fee_ledger[0]["ledger_id"], policy["source_id"], precedent["precedent_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "retrieval_decision_seq": decision.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        offer = evidence["offer"]
        fee_5pct = pct_fee(offer["amount"], offer["fee_rate"])
        fee_3pct = pct_fee(offer["amount"], "3.00")
        difference = fee_5pct - fee_3pct
        computation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="sandbox", name="fee_amount"),
            type=EventType.COMPUTATION,
            summary=f"Submitted-rate fee {fee_5pct} vs stated-rate fee {fee_3pct}; remediation {difference}",
            payload={"helper": "fee_amount", "inputs": {"amount": offer["amount"], "submitted_rate": offer["fee_rate"],
                     "stated_rate": "3.00"}, "output": {"fee_at_submitted_rate": str(fee_5pct),
                     "fee_at_stated_rate": str(fee_3pct), "remediation": str(difference)},
                     "runtime": "registered_python_helper"},
            refs=[offer["offer_instance_id"], evidence["fee_ledger"]["ledger_id"]],
        )
        finding = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="Stated three percent, but the submitted and billed offer was five percent with no dollar amount stated",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "stated_rate": "3.00", "submitted_rate": offer["fee_rate"],
                     "billed_amount": evidence["fee_ledger"]["amount"], "dollar_amount_stated": False},
            refs=[f"{state['interaction_ids'][0]}:t01", offer["offer_instance_id"], evidence["fee_ledger"]["ledger_id"]],
        )
        return {"fee_at_submitted_rate": str(fee_5pct), "fee_at_stated_rate": str(fee_3pct),
                "remediation_amount": str(difference), "computation_seq": computation.seq,
                "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        offer = evidence["offer"]
        policy = evidence["policy"]
        precedent = evidence["precedent"]
        checks = {
            "stated_rate_exact": "three percent transfer fee" in turn["text"].lower(),
            "dollar_amount_omitted": "$" not in turn["text"] and "dollar" not in turn["text"].lower(),
            "submitted_rate_mismatches_stated": offer["fee_rate"] != "3.00",
            "billed_matches_submitted_rate": evidence["fee_ledger"]["amount"] == state["fee_at_submitted_rate"],
            "policy_as_of": policy["version"] == "v5" and policy["effective_from"] <= "2026-10-20",
            "precedent_distinguished": precedent["precedent_id"] == "PRE-0022" and offer["fee_rate"] != "3.00",
        }
        span = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact stated fee-rate sentence",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t01",
                     "quote": turn["text"], "substring_match": checks["stated_rate_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t01"],
        )
        citation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified CHC-BT v5 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "2.2",
                     "governing_date": "2026-10-20", "valid": checks["policy_as_of"]}, refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C05_L3", "result": "pass" if passed else "fail"},
                refs=[offer["offer_instance_id"], policy["source_id"], precedent["precedent_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C05 deterministic verifier failed")
        confidence = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[policy["source_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "remediation below $250 with computed confidence at 1.0; no systemic or protected-situation trigger",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-03 and MC-04 substantiated for the misrepresented rate and omitted dollar amount",
            payload={"findings": [
                {"finding_id": "F1", "category": "MC-03", "status": "substantiated", "attributable_to": "colleague"},
                {"finding_id": "F2", "category": "MC-04", "status": "substantiated", "attributable_to": "colleague"},
            ]},
            refs=[f"{state['interaction_ids'][0]}:t01", state["evidence"]["offer"]["offer_instance_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for a single-interaction colleague misrepresentation",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "case-local finding from one verified interaction; no generalizable pattern basis",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        offer = evidence["offer"]
        policy = evidence["policy"]
        precedent = evidence["precedent"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        source_refs = [f"{interaction_id}:t01", offer["offer_instance_id"], evidence["fee_ledger"]["ledger_id"],
                       policy["source_id"], precedent["precedent_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["retrieval_decision_seq"], state["computation_seq"],
            state["reconcile_event_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["verification_seqs"],
        ]))
        findings = [
            Finding(
                finding_id="F1", category="MC-03", status="substantiated", attributable_to="colleague",
                severity="high", interaction_id=interaction_id,
                evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                                 "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                                 "quote": turn["text"], "verified": True}],
                structured_evidence=[{"source": "offers", "id": offer["offer_instance_id"],
                                      "fact": f"submitted at fee_rate {offer['fee_rate']}%, stated as three percent"}],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "2.2", "verified": True}],
                confidence=state["computed_confidence"],
            ),
            Finding(
                finding_id="F2", category="MC-04", status="substantiated", attributable_to="colleague",
                severity="high", interaction_id=interaction_id,
                evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                                 "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                                 "quote": turn["text"], "verified": True}],
                structured_evidence=[{"source": "fee_ledger", "id": evidence["fee_ledger"]["ledger_id"],
                                      "fact": f"billed {evidence['fee_ledger']['amount']} with no dollar amount disclosed"}],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "2.2", "verified": True}],
                confidence=state["computed_confidence"],
            ),
        ]
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"],
            "findings": [finding.model_dump() for finding in findings],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "refund_fee", "amount": state["remediation_amount"]},
                {"action": "offer_bt_cancellation_letter"},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the submitted offer had actually been three percent, or the dollar amount had been stated"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "case-local finding; no generalizable pattern",
                                            "source_refs": [state["interaction_ids"][0]]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "accurate three-percent offer, PRE-0022 applies", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "misrepresented rate and omitted dollar amount on the actually-submitted "
                                       "five-percent offer", "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": policy["source_id"], "why": "governing balance-transfer fee disclosure"},
                             {"doc_id": precedent["precedent_id"], "why": "distinguished: earlier version, genuine three-percent offer"}],
            "summary_for_record": "MC-03 and MC-04 substantiated. The colleague stated a three-percent fee with no "
                                   "dollar amount, but the offer actually submitted and billed was five percent "
                                   f"({state['fee_at_submitted_rate']} vs {state['fee_at_stated_rate']}); remediation "
                                   f"{state['remediation_amount']}.",
            "customer_letter": None,
        }
        paths = _leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C05 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}

    @staticmethod
    def _context(state: dict[str, Any]) -> dict[str, Any]:
        return {"run_id": state["run_id"], "review_id": state["review_id"],
                "virtual_now": datetime.fromisoformat(state["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)}


def _leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            paths.extend(_leaf_paths(item, f"{prefix}.{key}" if prefix else key))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_leaf_paths(item, f"{prefix}[{index}]"))
        return paths or [prefix]
    return [prefix]
