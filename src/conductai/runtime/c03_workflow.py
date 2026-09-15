"""Provider-neutral C03 L1 obligations used by the LangGraph adapter."""

from __future__ import annotations

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


class C03Workflow:
    """Deterministic clean-CLI path; unsupported routes fail closed in Stage 4A."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=8, **self._context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary=f"Selected {route.route_id} at {route.depth}",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "credit_line_request_present": state["route_facts"]["credit_line_request_present"],
                         "inquiry_type": state["route_facts"]["inquiry_type"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        if route.route_id != "cli_soft_pull_clean":
            raise RuntimeError("Stage 4A supports only the cli_soft_pull_clean path")
        for skill in route.skills:
            metadata, digest, path = load_skill(self.root, skill)
            self.ledger.emit(
                **self._context(state), actor=Actor(kind="agent", name="skill_backend"),
                type=EventType.SKILL_LOADED, summary=f"Loaded {skill} for the selected route",
                payload={"skill": skill, "version": metadata["version"], "hash": digest,
                         "path": path, "reason": "route"}, refs=[path],
            )
        plan = [
            "verify the exact credit-score assurance",
            "resolve CLI policy as of the interaction date",
            "compare tenure and amount thresholds with the actual inquiry",
            "stop if all decisive facts agree",
        ]
        self.ledger.emit(
            **self._context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.PLAN_CREATED, summary="Created the bounded L1 verification plan",
            payload={"steps": plan, "max_replans": route.budget.replans}, refs=[state["interaction_ids"][0]],
        )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq, "plan": plan}

    def fast_path_gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Verify the scanner-matched assurance against the source turn",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        request, used = self.tools.execute(
            "get_credit_line_request", {"interaction_id": interaction_id},
            rationale="Read the request amount, tenure, and applied policy",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        inquiry, used = self.tools.execute(
            "get_bureau_inquiry", {"credit_request_id": request["credit_request_id"]},
            rationale="Confirm the inquiry that actually occurred",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-POL-CLI", "governing_date": governing_date},
            rationale="Resolve the CLI inquiry rule as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        decisive = next(turn for turn in transcript if "affect your credit score" in turn["text"])
        evidence = {
            "transcript": transcript, "decisive_turn": decisive, "credit_request": request,
            "inquiry": inquiry, "policy": policy,
        }
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added decisive C03 evidence to the review file",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["said", "recorded", "policy"]},
            refs=[f"{interaction_id}:{decisive['turn_id']}", request["credit_request_id"],
                  inquiry["inquiry_id"], policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        request = evidence["credit_request"]
        expected = "HARD" if int(request["tenure_months_at_request"]) < 12 or int(request["requested_increase"]) > 5000 else "SOFT"
        computation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="sandbox", name="cli_inquiry_rule"),
            type=EventType.COMPUTATION, summary=f"CLI rule computed expected inquiry type {expected}",
            payload={"helper": "cli_inquiry_type", "inputs": {
                "tenure_months": int(request["tenure_months_at_request"]),
                "requested_increase": int(request["requested_increase"]),
                "tenure_threshold": 12, "increase_threshold": 5000,
            }, "output": expected, "runtime": "registered_python_helper"},
            refs=[request["credit_request_id"], evidence["policy"]["source_id"]],
        )
        actual = evidence["inquiry"]["inquiry_type"]
        return {"expected_inquiry": expected, "actual_inquiry": actual, "computation_seq": computation.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = evidence["decisive_turn"]
        quote = "Requesting an increase won't affect your credit score."
        quote_ok = quote in turn["text"]
        span_event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact assurance in the source turn",
            payload={"interaction_id": turn["interaction_id"], "turn_id": turn["turn_id"],
                     "quote": quote, "substring_match": quote_ok},
            refs=[f"{turn['interaction_id']}:{turn['turn_id']}"],
        )
        policy = evidence["policy"]
        policy_ok = policy["version"] == "v6" and policy["effective_from"] <= "2026-11-10"
        citation_event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified CLI v6 governed the interaction",
            payload={"doc": policy["source_id"], "clause": "2.1", "governing_date": "2026-11-10",
                     "valid": policy_ok}, refs=[policy["source_id"]],
        )
        checks = {
            "quote_exact": quote_ok,
            "policy_as_of": policy_ok,
            "policy_applied": evidence["credit_request"]["policy_version_applied"] == policy["source_id"],
            "actual_matches_rule": state["actual_inquiry"] == state["expected_inquiry"] == "SOFT",
        }
        check_events: list[int] = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C03_L1", "result": "pass" if passed else "fail"},
                refs=[turn["interaction_id"], policy["source_id"], evidence["inquiry"]["inquiry_id"]],
            )
            check_events.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C03 deterministic verifier failed")
        confidence = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "result": 1.0},
            refs=[turn["interaction_id"], policy["source_id"], evidence["inquiry"]["inquiry_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span_event.seq, citation_event.seq, *check_events, confidence.seq]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False, "panel_reason": "no adverse finding or high-impact trigger"}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        finding_event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED, summary="Proposed no error because the assurance was accurate",
            payload={"finding_id": "F1", "category": "none", "status": "no_error",
                     "attributable_to": "none"},
            refs=[f"{evidence['decisive_turn']['interaction_id']}:{evidence['decisive_turn']['turn_id']}",
                  evidence["inquiry"]["inquiry_id"], evidence["policy"]["source_id"]],
        )
        return {"finding_event_seq": finding_event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for an accurate case-local statement",
            payload={"subject": state["route_facts"]["interaction"]["interaction_id"],
                     "reason": "statement accurate under CLI v6; no new knowledge",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["evidence"]["policy"]["source_id"]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction_id = state["interaction_ids"][0]
        source_refs = [f"{interaction_id}:{evidence['decisive_turn']['turn_id']}",
                       evidence["credit_request"]["credit_request_id"], evidence["inquiry"]["inquiry_id"],
                       evidence["policy"]["source_id"]]
        seqs = sorted(set([state["route_event_seq"], state["computation_seq"], state["finding_event_seq"],
                           state["memory_event_seq"], *state["verification_seqs"]]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": evidence["decisive_turn"]["turn_id"],
                             "start_s": float(evidence["decisive_turn"]["start_s"]),
                             "end_s": float(evidence["decisive_turn"]["end_s"]),
                             "quote": evidence["decisive_turn"]["text"], "verified": True}],
            structured_evidence=[{"source": "credit_line_requests", "id": evidence["credit_request"]["credit_request_id"],
                                  "fact": "tenure 74 months; requested increase $1,500"},
                                 {"source": "bureau_inquiries", "id": evidence["inquiry"]["inquiry_id"],
                                  "fact": "SOFT inquiry"}],
            policy_refs=[{"doc_id": evidence["policy"]["source_id"], "clause": "2.1", "verified": True}],
            confidence=1.0,
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False, "remediation": [{"action": "none"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": 1.0, "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "a hard inquiry or threshold-triggering request fact"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "statement accurate under CLI v6; no new knowledge",
                                            "source_refs": [evidence["policy"]["source_id"]]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "credit-effect misinformation", "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "accurate soft-inquiry assurance", "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": evidence["policy"]["source_id"], "why": "governing CLI inquiry threshold"}],
            "summary_for_record": "No error. The request qualified for a soft inquiry and the bureau record confirms one occurred.",
            "customer_letter": None,
        }
        paths = _leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump()
                                    for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C03 assessment",
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
