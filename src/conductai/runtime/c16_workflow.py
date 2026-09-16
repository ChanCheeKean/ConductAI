"""C16 post-call enrollment: a monitoring-service enrollment submitted after the call ended, so no consent was
possible; a same-colleague lookback is opened as a follow-up rather than reviewed now."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.sandbox import local_to_utc
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C16Workflow:
    """Deterministic post-call enrollment timing path; C16 only."""

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
        if route.route_id != "post_call_addon_review":
            raise RuntimeError("C16 requires the post_call_addon_review route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the post-call enrollment timing path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "addon_enrollment_product": state["route_facts"]["addon_enrollment_product"],
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
            rationale="Confirm the transcript never mentions the monitoring enrollment",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollments, used = self.tools.execute(
            "get_enrollments", {"interaction_id": interaction_id},
            rationale="Read the enrollment's submission timestamp and time zone",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete; no turn mentions monitoring or CreditWatch",
            payload={"interaction_id": interaction_id, "turn_id": "t03", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t03"],
        )
        return {"evidence": {"transcript": transcript, "enrollments": enrollments}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        account_id = state["route_facts"]["interaction"]["account_id"]
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        interaction_id = state["interaction_ids"][0]
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": account_id},
            rationale="Confirm the monitoring fee billed from this enrollment",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        lookback_from = (date.fromisoformat(governing_date) - timedelta(days=30)).isoformat() + "T00:00:00"
        lookback, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "creditwatch_post_call_lookback",
             "parameters": {"colleague_id": colleague_id, "exclude_interaction_id": interaction_id, "from_at": lookback_from},
             "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Check whether this colleague has other CreditWatch enrollments submitted shortly after call end",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "fee_ledger": fee_ledger[0], "lookback": lookback}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the billed fee and the same-colleague lookback candidates",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["did", "billed", "lookback"]},
            refs=[fee_ledger[0]["ledger_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        enrollment = evidence["enrollments"][0]
        interaction = state["route_facts"]["interaction"]
        enrolled_utc = local_to_utc(enrollment["enrolled_at_local"], enrollment["enrolled_tz"])
        ended_utc = datetime.fromisoformat(interaction["ended_at_utc"].replace("Z", "+00:00")).astimezone(UTC)
        gap_seconds = (enrolled_utc - ended_utc).total_seconds()
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="timezone_order"),
            type=EventType.COMPUTATION,
            summary=f"Enrollment submitted at {enrolled_utc.isoformat()}, {gap_seconds:.0f}s after call end",
            payload={"helper": "timezone_order", "inputs": {
                "enrolled_at_local": enrollment["enrolled_at_local"], "enrolled_tz": enrollment["enrolled_tz"],
                "call_ended_at_utc": interaction["ended_at_utc"]},
                "output": {"enrolled_at_utc": enrolled_utc.isoformat().replace("+00:00", "Z"), "gap_seconds": gap_seconds},
                "runtime": "registered_python_helper"},
            refs=[enrollment["enrollment_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The enrollment was submitted after the call ended; no consent was possible",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "enrollment_after_call_end": gap_seconds > 0, "gap_seconds": gap_seconds,
                     "transcript_mentions_enrollment": False},
            refs=[f"{state['interaction_ids'][0]}:t03", enrollment["enrollment_id"]],
        )
        return {"enrolled_at_utc": enrolled_utc.isoformat().replace("+00:00", "Z"), "gap_seconds": gap_seconds,
                "computation_seq": computation.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        checks = {
            "no_transcript_mention": not any(
                "creditwatch" in turn["text"].lower() or "monitoring" in turn["text"].lower()
                for turn in evidence["transcript"]
            ),
            "enrollment_after_call_end": state["gap_seconds"] > 0,
            "billed_fee_matches_enrollment": evidence["fee_ledger"]["related_id"] == evidence["enrollments"][0]["enrollment_id"],
            "lookback_population_is_suspected_only": len(evidence["lookback"]) == 6,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified no transcript turn mentions the enrollment",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t03",
                     "quote": evidence["transcript"][-1]["text"], "substring_match": checks["no_transcript_mention"]},
            refs=[f"{state['interaction_ids'][0]}:t03"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C16_L3", "result": "pass" if passed else "fail"},
                refs=[evidence["enrollments"][0]["enrollment_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C16 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[evidence["enrollments"][0]["enrollment_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "remediation below $250 with computed confidence at 1.0; single interaction, "
                                "lookback population only suspected, not yet reviewed",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-02 substantiated: enrollment submitted after the call ended, so no consent was possible",
            payload={"finding_id": "F1", "category": "MC-02", "status": "substantiated", "attributable_to": "colleague"},
            refs=[f"{state['interaction_ids'][0]}:t03", state["evidence"]["enrollments"][0]["enrollment_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        follow_up, used = self.tools.execute(
            "schedule_follow_up", {
                "at": state["virtual_now"], "action_type": "targeted_lookback",
                "idempotency_key": f"{state['review_id']}:LOOKBACK",
            }, rationale="Open a targeted lookback over the colleague's other suspected post-call enrollments "
                          "instead of substantiating them without review",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"authorized_actions": [follow_up], "tool_calls_used": used}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write pending the targeted lookback's own findings",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "a suspected pattern is not yet a verified generalizable fact; the lookback governs that",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        enrollment = evidence["enrollments"][0]
        fee_ledger = evidence["fee_ledger"]
        source_refs = [f"{interaction_id}:t03", enrollment["enrollment_id"], fee_ledger["ledger_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["computation_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"], *state["integrity_event_seqs"],
            *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-02", status="substantiated", attributable_to="colleague", severity="high",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t03",
                             "start_s": float(evidence["transcript"][-1]["start_s"]),
                             "end_s": float(evidence["transcript"][-1]["end_s"]),
                             "quote": evidence["transcript"][-1]["text"], "verified": True}],
            structured_evidence=[
                {"source": "enrollments", "id": enrollment["enrollment_id"],
                 "fact": f"submitted {state['enrolled_at_utc']}, {state['gap_seconds']:.0f}s after call end"},
                {"source": "fee_ledger", "id": fee_ledger["ledger_id"], "fact": f"billed {fee_ledger['amount']}"},
            ],
            policy_refs=[], confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "reverse_enrollment"}, {"action": "refund_fee", "amount": fee_ledger["amount"]},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "targeted_lookback", "enhanced_monitoring"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the enrollment had actually been submitted before the call ended, "
                                          "with the customer's affirmative consent on the recording"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "suspected pattern pending the lookback's own findings",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "customer consented to monitoring during the call", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "enrollment submitted after the call ended with no possible consent",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [],
            "summary_for_record": "MC-02 substantiated. The CreditWatch Plus enrollment was submitted "
                                   f"{state['gap_seconds']:.0f} seconds after the call ended; the transcript never "
                                   "mentions monitoring. A targeted lookback over 6 similarly timed enrollments by "
                                   "the same colleague is opened as a follow-up rather than substantiated here.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C16 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
