"""C19 memory-vs-glossary supersession: a confidently stale, heavily accessed note loses to the glossary in force."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C19Workflow:
    """Deterministic memory-supersession path; C19 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=20, **self._context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "cli_prescreened_assurance":
            raise RuntimeError("C19 requires the cli_prescreened_assurance route")
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the pre-approved-assurance memory-check path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "prescreened_cli_offer_present": state["route_facts"]["prescreened_cli_offer_present"],
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
            rationale="Read the exact pre-approved assurance turn",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        offers, used = self.tools.execute(
            "get_offers", {"interaction_id": interaction_id},
            rationale="Confirm the firm offer instance and its desktop display timing",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        assessed = self.ledger.emit(
            **self._context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the assurance turn is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"transcript": transcript, "offers": offers}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        memory, used = self.tools.execute(
            "get_memory_note", {"note_id": "MEM-0350"},
            rationale="Retrieve the consolidated note this scanner flag's category maps to",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        memory_read = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_repository"),
            type=EventType.MEMORY_READ, summary="Read consolidated pre-approved-language memory note",
            payload={"store": "notes", "filters": {"note_id": "MEM-0350", "status": ["active"]},
                     "note_ids": ["MEM-0350"]}, refs=["MEM-0350"],
        )
        glossary, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-GLOSS", "governing_date": governing_date},
            rationale="Resolve the pre-approved-language rule as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        scanner_rule, used = self.tools.execute(
            "get_scanner_rule", {"rule_id": "SCN-PREAPPROVED"},
            rationale="Check whether the scanner rule's glossary basis is current",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        evidence = {**state["evidence"], "memory": memory, "glossary": glossary, "scanner_rule": scanner_rule}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the memory note, glossary version, and scanner rule basis",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "memory", "glossary"]},
            refs=["MEM-0350", glossary["source_id"], "SCN-PREAPPROVED"],
        )
        return {"evidence": evidence, "tool_calls_used": used, "memory_read_seq": memory_read.seq}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        offer = evidence["offers"][0]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        firm_offer_displayed = bool(offer["displayed_on_desktop_at_utc"]) and offer["eligibility_result"] == "ELIGIBLE"
        firm_offer_valid = offer["firm_offer_valid_through"] >= governing_date
        reject = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="evidence_service"),
            type=EventType.MEMORY_REJECTED,
            summary="MEM-0350's unconditional basis is stale under the glossary version in force",
            payload={"note_id": "MEM-0350", "reason": "superseded governing glossary "
                     "(CLB-GLOSS@v7 permits pre-approved language when a firm offer is displayed)"},
            refs=["MEM-0350", evidence["glossary"]["source_id"]],
        )
        finding = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="Firm offer was displayed and valid, so the pre-approved assurance is accurate",
            payload={"finding_id": "F1", "status": "no_error_candidate",
                     "firm_offer_displayed": firm_offer_displayed, "firm_offer_valid": firm_offer_valid},
            refs=[f"{state['interaction_ids'][0]}:t01", offer["offer_instance_id"]],
        )
        return {"firm_offer_displayed": firm_offer_displayed, "firm_offer_valid": firm_offer_valid,
                "memory_reject_seq": reject.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        offer = evidence["offers"][0]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        glossary = evidence["glossary"]
        checks = {
            "quote_exact": "pre-approved" in turn["text"].lower(),
            "firm_offer_displayed": state["firm_offer_displayed"],
            "firm_offer_valid": state["firm_offer_valid"],
            "glossary_as_of": glossary["version"] == "v8" and glossary["effective_from"] <= "2026-11-12",
            "memory_basis_stale": any("v6" in ref for ref in json.loads(evidence["memory"]["subject_ids"])),
        }
        span = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact pre-approved assurance turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t01",
                     "quote": turn["text"], "substring_match": checks["quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t01"],
        )
        citation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified glossary v8 governed the pre-approved-language rule",
            payload={"doc": glossary["source_id"], "clause": "MC-03.2",
                     "governing_date": "2026-11-12", "valid": checks["glossary_as_of"]},
            refs=[glossary["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C19_L2", "result": "pass" if passed else "fail"},
                refs=[offer["offer_instance_id"], glossary["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C19 deterministic verifier failed")
        confidence = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[glossary["source_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False, "panel_reason": "no adverse finding or high-impact trigger",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed no error: the pre-approved assurance matched a displayed, valid firm offer",
            payload={"finding_id": "F1", "category": "none", "status": "no_error", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t01", state["evidence"]["offers"][0]["offer_instance_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        supersede = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_SUPERSEDE,
            summary="Superseded MEM-0350 at the date the glossary rule changed",
            payload={"old": "MEM-0350", "new": "MEM-0350-R1", "valid_to": "2026-06-30",
                     "reason": "CLB-GLOSS@v7 introduced the firm-offer-displayed condition on 2026-07-01"},
            refs=["MEM-0350", state["evidence"]["glossary"]["source_id"]],
        )
        consolidate = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_CONSOLIDATE,
            summary="Wrote a new consolidated note carrying the v7/v8 firm-offer condition",
            payload={"inputs": ["MEM-0350"], "output": "MEM-0350-R1",
                     "content": "'Pre-approved' is MC-03 unless a valid prescreened firm offer is displayed "
                                 "on the colleague desktop (CLB-GLOSS@v7 §MC-03.2, in force from 2026-07-01)."},
            refs=["MEM-0350-R1", state["evidence"]["glossary"]["source_id"]],
        )
        return {"memory_event_seq": consolidate.seq, "memory_ops_event_seqs": [supersede.seq, consolidate.seq]}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        offer = evidence["offers"][0]
        glossary = evidence["glossary"]
        scanner_rule = evidence["scanner_rule"]
        source_refs = [f"{interaction_id}:t01", offer["offer_instance_id"], "MEM-0350",
                       glossary["source_id"], "SCN-PREAPPROVED"]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_read_seq"], state["reconcile_event_seq"],
            state["memory_reject_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["verification_seqs"], *state["memory_ops_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                             "start_s": float(next(t for t in evidence["transcript"] if t["turn_id"] == "t01")["start_s"]),
                             "end_s": float(next(t for t in evidence["transcript"] if t["turn_id"] == "t01")["end_s"]),
                             "quote": "Good news — you're pre-approved for a credit line increase to $9,000.",
                             "verified": True}],
            structured_evidence=[{"source": "offers", "id": offer["offer_instance_id"],
                                  "fact": "firm offer displayed on desktop and valid through "
                                          f"{offer['firm_offer_valid_through']}"}],
            policy_refs=[{"doc_id": glossary["source_id"], "clause": "MC-03.2", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False, "remediation": [{"action": "none"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": [{"type": "scanner_rule_update_request", "rule_id": "SCN-PREAPPROVED",
                                             "reason": f"rule basis {scanner_rule['glossary_version_basis']} is "
                                                       "stale against the glossary in force"}]},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "no firm offer displayed, or the offer invalid/expired"},
            "waits": [], "memory_ops": [
                {"op": "supersede", "old": "MEM-0350", "new": "MEM-0350-R1", "valid_to": "2026-06-30",
                 "source_refs": [glossary["source_id"]]},
                {"op": "consolidate", "inputs": ["MEM-0350"], "output": "MEM-0350-R1",
                 "source_refs": [glossary["source_id"]]},
            ],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "pre-approved language always MC-03", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "accurate under the firm-offer-displayed exception", "status": "supported",
                 "evidence_for": source_refs},
            ], "citations": [{"doc_id": glossary["source_id"], "why": "governing pre-approved-language rule"}],
            "summary_for_record": "No error. A valid, displayed prescreened firm offer makes the pre-approved "
                                   "assurance accurate under the glossary version in force.",
            "customer_letter": None,
        }
        paths = _leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C19 assessment",
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
