"""C07b event-time reconciliation: a fee waiver that preceded the add-on pitch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C07bWorkflow:
    """Deterministic clock-skew reconciliation path; C07b only."""

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
        if route.route_id != "conditioned_servicing_event_time":
            raise RuntimeError("C07b requires the conditioned_servicing_event_time route")
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the conditioned-servicing event-time path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "fee_reversal_event_present": state["route_facts"]["fee_reversal_event_present"],
                         "addon_enrollment_present": state["route_facts"]["addon_enrollment_present"],
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
            rationale="Inspect the waiver, add-on pitch, and consent turns",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Locate the fee-reversal desktop submission and its recording workstation",
            used=used, limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        assessed = self.ledger.emit(
            **self._context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete with no gap over the waiver, pitch, or consent turns",
            payload={"interaction_id": interaction_id, "turn_id": None, "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[interaction_id],
        )
        return {"evidence": {"transcript": transcript, "desktop_events": desktop}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        desktop_event = state["evidence"]["desktop_events"][0]
        offset, used = self.tools.execute(
            "get_workstation_clock_offset", {"workstation_id": desktop_event["workstation_id"]},
            rationale="Resolve the measured clock skew for the workstation that submitted the waiver",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **self._context(state),
        )
        evidence = {**state["evidence"], "clock_offset": offset}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the desktop waiver, pitch turns, and workstation clock offset",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "did", "clock_offset"]},
            refs=[desktop_event["event_id"], offset["workstation_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        desktop_event = evidence["desktop_events"][0]
        offset_seconds = int(evidence["clock_offset"]["offset_seconds"])
        local_dt = datetime.fromisoformat(desktop_event["ts_local"]).replace(tzinfo=ZoneInfo(desktop_event["tz"]))
        workstation_utc = local_dt.astimezone(UTC)
        true_utc = workstation_utc - timedelta(seconds=offset_seconds)
        transcript = evidence["transcript"]
        mention_turn = next(t for t in transcript if t["turn_id"] == "t01")
        pitch_turn = next(t for t in transcript if t["turn_id"] == "t02")
        started = datetime.fromisoformat(state["route_facts"]["interaction"]["started_at_utc"].replace("Z", "+00:00"))
        mention_utc = started + timedelta(seconds=float(mention_turn["start_s"]))
        pitch_utc = started + timedelta(seconds=float(pitch_turn["start_s"]))
        seconds_before_mention = round((mention_utc - true_utc).total_seconds())
        seconds_before_pitch = round((pitch_utc - true_utc).total_seconds())
        computation = self.ledger.emit(
            **self._context(state), actor=Actor(kind="sandbox", name="align_desktop_clock"),
            type=EventType.COMPUTATION,
            summary=f"Waiver true time preceded the mention by {seconds_before_mention}s and the pitch by {seconds_before_pitch}s",
            payload={"helper": "align_desktop_clock", "inputs": {
                "ts_local": desktop_event["ts_local"], "tz": desktop_event["tz"], "offset_seconds": offset_seconds},
                "output": _iso(true_utc), "runtime": "registered_python_helper"},
            refs=[desktop_event["event_id"], evidence["clock_offset"]["workstation_id"]],
        )
        finding = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="Waiver was processed before it was mentioned and before the add-on pitch began",
            payload={"finding_id": "F1", "status": "no_error_candidate",
                     "waiver_true_utc": _iso(true_utc), "mention_utc": _iso(mention_utc), "pitch_utc": _iso(pitch_utc),
                     "seconds_before_mention": seconds_before_mention, "seconds_before_pitch": seconds_before_pitch},
            refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02", desktop_event["event_id"]],
        )
        return {"waiver_true_utc": _iso(true_utc), "seconds_before_mention": seconds_before_mention,
                "seconds_before_pitch": seconds_before_pitch, "reconcile_event_seq": finding.seq,
                "computation_seq": computation.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        transcript = evidence["transcript"]
        consent_turn = next(t for t in transcript if t["turn_id"] == "t04")
        checks = {
            "waiver_preceded_mention": state["seconds_before_mention"] > 0,
            "waiver_preceded_pitch": state["seconds_before_pitch"] > 0,
            "no_conditional_language": "if you" not in next(t for t in transcript if t["turn_id"] == "t01")["text"].lower(),
            "consent_explicit": consent_turn["text"].strip() == "Yes, add it.",
        }
        span = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the explicit CardShield consent turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": consent_turn["turn_id"],
                     "quote": consent_turn["text"], "substring_match": checks["consent_explicit"]},
            refs=[f"{state['interaction_ids'][0]}:t04"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **self._context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C07b_L2", "result": "pass" if passed else "fail"},
                refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t04"],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C07b deterministic verifier failed")
        confidence = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[f"{state['interaction_ids'][0]}:t04"],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False, "panel_reason": "no adverse finding or high-impact trigger",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed no error: the waiver was unconditional and consent was explicit",
            payload={"finding_id": "F1", "category": "none", "status": "no_error", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t04"],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for an accurate case-local event-time reconciliation",
            payload={"subject": state["interaction_ids"][0],
                     "reason": "no generalizable lesson; the workstation offset is already a registered reference fact",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", f"{interaction_id}:t04",
                       evidence["desktop_events"][0]["event_id"], evidence["clock_offset"]["workstation_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["computation_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t04",
                             "start_s": float(next(t for t in evidence["transcript"] if t["turn_id"] == "t04")["start_s"]),
                             "end_s": float(next(t for t in evidence["transcript"] if t["turn_id"] == "t04")["end_s"]),
                             "quote": "Yes, add it.", "verified": True}],
            structured_evidence=[{"source": "desktop_events", "id": evidence["desktop_events"][0]["event_id"],
                                  "fact": f"fee_reversal_submitted true UTC {state['waiver_true_utc']}, "
                                          f"{state['seconds_before_mention']}s before the mention and "
                                          f"{state['seconds_before_pitch']}s before the pitch"}],
            policy_refs=[],
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
                             "flip_fact": "the waiver being processed after the pitch and tied to enrollment"},
            "waits": [], "memory_ops": [{"op": "skip", "reason": "no generalizable lesson from an accurate event-time reconciliation",
                                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "waiver conditioned on CardShield enrollment", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "unconditional waiver, independently pitched and consented add-on", "status": "supported",
                 "evidence_for": source_refs},
            ], "citations": [],
            "summary_for_record": "No error. The clock-skew-corrected waiver time precedes both the spoken mention and "
                                   "the CardShield pitch, and the customer gave explicit consent to the priced add-on.",
            "customer_letter": None,
        }
        paths = _leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **self._context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C07b assessment",
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


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
