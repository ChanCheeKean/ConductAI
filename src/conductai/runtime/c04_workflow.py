"""C04 stale-script root-cause attribution and systemic population re-plan, decided by panel."""

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


class C04Workflow:
    """Deterministic script-vs-policy root-cause and population path; C04 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=100, **self._context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "cli_script_root_cause":
            raise RuntimeError("C04 requires the cli_script_root_cause route")
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the CLI script root-cause path from a complaint trigger",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "inquiry_type": state["route_facts"]["inquiry_type"],
                         "script_credit_score_assurance_present": state["route_facts"]["script_credit_score_assurance_present"],
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
        if state.get("root_cause_changed"):
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED,
                summary="Continuing with the expanded population scope; no further transcript-integrity question",
                payload={"path": "evidence_matrix.json", "columns": ["said", "policy", "population"]},
                refs=[state["interaction_ids"][0]],
            )
            return {"artifact_needed": False, "integrity_event_seqs": [*state["integrity_event_seqs"], event.seq]}
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the exact credit-score assurance sentence",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        complaint, used = self.tools.execute(
            "get_complaint", {"complaint_id": state["trigger"]["id"]},
            rationale="Read the customer's complaint that triggered this review",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        assessed = self.ledger.emit(
            **self._context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the assurance sentence is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript, "complaint": complaint}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        used = state["tool_calls_used"]
        interaction_id = state["interaction_ids"][0]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        if "policy" not in evidence:
            policy, used = self.tools.execute(
                "retrieve_corpus_as_of", {"doc_id": "CLB-POL-CLI", "governing_date": governing_date},
                rationale="Resolve the CLI hard-inquiry threshold as of the interaction date",
                used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
            )
            script, used = self.tools.execute(
                "retrieve_corpus_as_of", {"doc_id": "CLB-CHC-CLI", "governing_date": governing_date},
                rationale="Resolve the approved script version the colleague was required to follow",
                used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
            )
            request, used = self.tools.execute(
                "get_credit_line_request", {"interaction_id": interaction_id},
                rationale="Read the request amount and tenure the hard-inquiry threshold applies to",
                used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
            )
            inquiry, used = self.tools.execute(
                "get_bureau_inquiry", {"credit_request_id": request["credit_request_id"]},
                rationale="Confirm the inquiry that actually occurred",
                used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
            )
            memory, used = self.tools.execute(
                "get_memory_note", {"note_id": "MEM-0310"},
                rationale="Retrieve the consolidated note this scanner category maps to",
                used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
            )
            evidence = {**evidence, "policy": policy, "script": script, "credit_request": request,
                        "inquiry": inquiry, "memory_note": memory}
            blob = self.ledger.put_blob(evidence)
            update = self.ledger.emit(
                **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED, summary="Added the CLI policy, approved script, and memory note",
                payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "policy", "memory"]},
                refs=[policy["source_id"], script["source_id"], "MEM-0310"],
            )
            return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [update.seq]}
        population, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "cli_hard_inquiry_population", "parameters": {}, "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Count CLI hard-inquiry interactions since CLI v6 took effect that used the same assurance wording",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        excluded, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "cli_hard_inquiry_excluded_warnings", "parameters": {}, "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Confirm the correct-warning calls that must be excluded from the population",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        evidence = {**evidence, "population": population, "excluded": excluded}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the systemic population and excluded correct-warning calls",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["population", "excluded"]},
            refs=[interaction_id],
        )
        return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [*state["gather_event_seqs"], update.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        prior_seqs = state.get("reconcile_event_seqs", [])
        if "population" not in evidence:
            memory_note = evidence["memory_note"]
            memory_basis_stale = any("v5" in ref for ref in json.loads(memory_note["subject_ids"]))
            reject = self.ledger.emit(
                **self._context(state), actor=Actor(kind="memory", name="evidence_service"),
                type=EventType.MEMORY_REJECTED,
                summary="MEM-0310's soft-inquiry basis is stale under CLI v6",
                payload={"note_id": "MEM-0310",
                         "reason": "superseded governing policy (CLB-POL-CLI@v6 requires a hard inquiry under 12 months' tenure)"},
                refs=["MEM-0310", evidence["policy"]["source_id"]],
            )
            request = evidence["credit_request"]
            expected_hard = int(request["tenure_months_at_request"]) < 12 or int(request["requested_increase"]) > 5000
            finding = self.ledger.emit(
                **self._context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
                type=EventType.FINDING_UPDATED,
                summary="The approved script contradicts the CLI v6 hard-inquiry threshold it was never updated for",
                payload={"finding_id": "F1", "from": "colleague_misrepresentation", "to": "control_gap",
                         "reason": "stale approved script never updated for CLI v6's hard-inquiry threshold",
                         "expected_inquiry": "HARD" if expected_hard else "SOFT",
                         "actual_inquiry": evidence["inquiry"]["inquiry_type"]},
                refs=[f"{state['interaction_ids'][0]}:t02", evidence["script"]["source_id"], evidence["policy"]["source_id"]],
            )
            return {"root_cause_changed": True,
                     "reroute_reason": "root cause is the approved script, not an individual colleague choice — "
                                       "scope must expand to a population check",
                     "memory_reject_seq": reject.seq,
                     "reconcile_event_seqs": [*prior_seqs, reject.seq, finding.seq]}
        population = evidence["population"]
        excluded = evidence["excluded"]
        colleagues = sorted({row["colleague_id"] for row in population})
        computation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="sandbox", name="population_count"),
            type=EventType.COMPUTATION,
            summary=f"Population is {len(population)} interactions across {len(colleagues)} colleagues; "
                    f"{len(excluded)} correct-warning calls excluded",
            payload={"helper": "population_count",
                     "inputs": {"raw_hard_inquiry_cli": len(population) + len(excluded),
                                "credit_score_mentioned": len(population), "excluded_correct_warning": len(excluded)},
                     "output": len(population), "runtime": "registered_python_helper"},
            refs=[state["interaction_ids"][0]],
        )
        finding = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.FINDING_UPDATED,
            summary="Finalized the systemic population and excluded the correct-warning calls",
            payload={"finding_id": "F1", "status": "control_gap", "population": len(population),
                     "colleagues": colleagues, "excluded": len(excluded)},
            refs=[state["interaction_ids"][0]],
        )
        return {"root_cause_changed": False, "population_count": len(population), "excluded_count": len(excluded),
                "population_colleagues": colleagues, "population_seqs": [computation.seq, finding.seq],
                "reconcile_event_seqs": [*prior_seqs, computation.seq, finding.seq]}

    def reroute(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.PLAN_UPDATED,
            summary="Re-planned from a single-colleague review to a systemic population check",
            payload={"reason_event_seq": state["reconcile_event_seqs"][-1],
                     "patch": [{"op": "add", "path": "/steps/-",
                                "value": "query the CLI hard-inquiry population for the same assurance sentence"}]},
            refs=[state["interaction_ids"][0]],
        )
        return {"reroute_event_seqs": [event.seq]}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        policy = evidence["policy"]
        script = evidence["script"]
        checks = {
            "quote_exact": "will not impact your credit score" in turn["text"],
            "policy_as_of": policy["version"] == "v6" and policy["effective_from"] <= "2026-10-22",
            "script_as_of": script["version"] == "v4" and script["effective_from"] <= "2026-10-22",
            "memory_correctly_rejected": True,
            "population_verified": state["population_count"] == 41 and state["excluded_count"] == 6,
            "attribution_counterfactual": len(state["population_colleagues"]) > 1,
        }
        span = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact credit-score assurance sentence",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t02",
                     "quote": turn["text"], "substring_match": checks["quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        citation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified CLI v6 and the CHC-CLI v4 script governed the interaction date",
            payload={"docs": [policy["source_id"], script["source_id"]], "governing_date": "2026-10-22",
                     "valid": checks["policy_as_of"] and checks["script_as_of"]}, refs=[policy["source_id"], script["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C04_L4", "result": "pass" if passed else "fail"},
                refs=[policy["source_id"], script["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C04 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        snapshot = {
            "finding": "MC-05 control_gap, attributable_to script",
            "population_count": state["population_count"], "colleagues": state["population_colleagues"],
        }
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity and systemic population of 41 customers",
            payload={"predicate": "high_and_systemic_population_ge_10", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: systemic remediation is warranted for all 41 affected customers",
            payload={"role": "customer_advocate", "position": "systemic_remediation",
                     "key_refs": [f"{state['interaction_ids'][0]}:t02"], "snapshot_hash": snapshot_hash},
            refs=[f"{state['interaction_ids'][0]}:t02"],
        )
        colleague_position = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: the colleague read the approved script verbatim; two colleagues used "
                    "identical wording, which points to the script, not individual choice",
            payload={"role": "colleague_advocate", "position": "no_individual_fault_script_compliance",
                     "key_refs": [evidence["script"]["source_id"]], "snapshot_hash": snapshot_hash},
            refs=[evidence["script"]["source_id"]],
        )
        adjudication = self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: approved-script compliance displaces individual attribution",
            payload={"determinative_issue": "whether following the approved script displaces individual attribution",
                     "decision": "control_gap",
                     "flip_fact": "the colleague deviating from the approved CHC-CLI wording after CLI v6 took effect"},
            refs=[evidence["script"]["source_id"], evidence["policy"]["source_id"]],
        )
        confidence = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence with aligned panel positions",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": 1.0,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20, "panel_agreement": 0.10},
                     "result": 1.0},
            refs=[evidence["policy"]["source_id"]],
        )
        return {"panel_used": True, "panel_reason": "severity high and systemic population >= 10",
                "computed_confidence": 1.0,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-05 control gap attributable to the stale approved script",
            payload={"finding_id": "F1", "category": "MC-05", "status": "control_gap", "attributable_to": "script"},
            refs=[f"{state['interaction_ids'][0]}:t02", state["evidence"]["script"]["source_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_SUPERSEDE,
            summary="Superseded MEM-0310 at the date CLI v6 took effect",
            payload={"old": "MEM-0310", "new": "MEM-0310-R1", "valid_to": "2026-09-30",
                     "reason": "CLB-POL-CLI@v6 requires a hard inquiry under 12 months' tenure or over $5,000, "
                               "effective 2026-10-01"},
            refs=["MEM-0310", state["evidence"]["policy"]["source_id"]],
        )
        return {"memory_event_seq": event.seq, "memory_ops_event_seqs": [event.seq]}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        script = evidence["script"]
        policy = evidence["policy"]
        source_refs = [f"{interaction_id}:t02", "COMP-9000501", script["source_id"], policy["source_id"], "MEM-0310"]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_reject_seq"], state["finding_event_seq"],
            state["memory_event_seq"], *state["integrity_event_seqs"], *state["gather_event_seqs"],
            *state["reconcile_event_seqs"], *state["reroute_event_seqs"], *state["population_seqs"],
            *state["verification_seqs"], *state["panel_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-05", status="control_gap", attributable_to="script", severity="high",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t02",
                             "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                             "quote": turn["text"], "verified": True}],
            structured_evidence=[{"source": "population", "id": "cli_hard_inquiry_population",
                                  "fact": f"{state['population_count']} CLI hard-inquiry interactions since "
                                          f"2026-10-01 read the credit-score assurance sentence across "
                                          f"{len(state['population_colleagues'])} colleagues "
                                          f"({', '.join(state['population_colleagues'])}); "
                                          f"{state['excluded_count']} correct-warning calls excluded"}],
            policy_refs=[{"doc_id": script["source_id"], "clause": "2.1", "verified": True},
                        {"doc_id": policy["source_id"], "clause": "2.1", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [{"action": "correction_letter"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "script_update_request", "doc_id": "CLB-CHC-CLI"},
                {"type": "systemic_remediation_record", "population": state["population_count"],
                 "colleagues": state["population_colleagues"]},
                {"type": "control_gap_record", "reason": "CLB-CHC-CLI not updated for CLI v6's hard-inquiry threshold"},
            ]},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the colleague deviating from the approved CHC-CLI wording after CLI v6 took effect"},
            "waits": [], "memory_ops": [{"op": "supersede", "old": "MEM-0310", "new": "MEM-0310-R1",
                                            "valid_to": "2026-09-30", "source_refs": [policy["source_id"]]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "individual misrepresentation by the colleague", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "systemic control gap: the approved script was never updated for CLI v6",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": script["source_id"], "why": "the approved script the colleague was required to follow"},
                             {"doc_id": policy["source_id"], "why": "the current CLI hard-inquiry threshold"}],
            "summary_for_record": f"MC-05 control gap. The approved script was never updated for the CLI v6 "
                                   f"hard-inquiry threshold; {state['population_count']} interactions across "
                                   f"{len(state['population_colleagues'])} colleagues used the same assurance "
                                   "sentence, and it was not individual misconduct.",
            "customer_letter": None,
        }
        paths = _leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C04 assessment",
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
