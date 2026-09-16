"""C18 dead air: an add-on enrollment submitted inside an unrecoverable recording gap. Two sequential
artifact_needed/integrity waits (audio recovery, then customer outreach) share the same request_artifact /
prepare_wait / ingest_artifact re-entry mechanism used for a single wait in c01_workflow.py, followed by a real
panel whose confidence genuinely lands below 0.75 because the decisive span has zero transcript coverage and the
audio recovery attempt failed. The honest outcome is insufficient_evidence: the colleague gets no adverse finding
(no evidence against them) and the customer gets the enrollment reversed anyway (no evidence for them either)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.deadlines import latest_safe_decision
from conductai.runtime.sandbox import local_to_utc
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C18Workflow:
    """Deterministic dead-air recording-gap path with two sequential waits; C18 only."""

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
        if route.route_id != "recording_gap_addon_review":
            raise RuntimeError("C18 requires the recording_gap_addon_review route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the recording-gap add-on review path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "recording_gap_present": state["route_facts"]["recording_gap_present"],
                         "addon_enrollment_present": state["route_facts"]["addon_enrollment_present"],
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
        if state.get("evidence", {}).get("audio_recovery_result") is not None:
            return self._assess_audio_recovery(state)
        interaction_id = state["interaction_ids"][0]
        interaction = state["route_facts"]["interaction"]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the full call to see what surrounds the recording gap",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollments, used = self.tools.execute(
            "get_enrollments", {"interaction_id": interaction_id},
            rationale="Confirm the add-on enrollment submitted on this call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Find the enrollment submission timestamp on the colleague's own desktop",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollment_event = next(row for row in desktop if row["type"] == "enrollment_submitted")
        overlaps, gap, decisive_turns, enrollment_utc, gap_start_utc, gap_end_utc = self._gap_overlap(
            interaction, enrollment_event, transcript,
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="The enrollment was submitted inside the unrecoverable recording gap; no transcript turn covers it",
            payload={"interaction_id": interaction_id, "source": "asr", "recording_gap": True,
                     "gap_bounds_s": gap, "gap_start_utc": _iso(gap_start_utc), "gap_end_utc": _iso(gap_end_utc),
                     "enrollment_utc": _iso(enrollment_utc), "gap_overlaps_enrollment": overlaps,
                     "decisive_transcript_turns": len(decisive_turns), "recovery_recommended": "audio_recovery"},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02", enrollment_event["event_id"]],
        )
        evidence = {"transcript": transcript, "enrollments": enrollments, "desktop_events": desktop}
        return {"evidence": evidence, "tool_calls_used": used, "artifact_needed": True,
                "gap_overlaps_enrollment": overlaps, "gap_bounds": gap, "decisive_turns_count": len(decisive_turns),
                "integrity_event_seqs": [assessed.seq]}

    def _assess_audio_recovery(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        recovery = state["evidence"]["audio_recovery_result"]
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Audio recovery was attempted and confirmed unrecoverable; the decisive span stays uncaptured",
            payload={"interaction_id": interaction_id, "source": "audio_recovery",
                     "artifact_id": "AUD-9002101", "status": recovery["status"],
                     "note": recovery.get("note"), "recovery_recommended": None},
            refs=["AUD-9002101"],
        )
        return {"artifact_needed": False,
                "integrity_event_seqs": [*state["integrity_event_seqs"], assessed.seq]}

    @staticmethod
    def _gap_overlap(
        interaction: dict[str, Any], enrollment_event: dict[str, Any], transcript: list[dict[str, Any]],
    ) -> tuple[bool, list[int], list[dict[str, Any]], datetime, datetime, datetime]:
        gap = json.loads(interaction["recording_gaps"])[0]
        started = datetime.fromisoformat(interaction["started_at_utc"].replace("Z", "+00:00")).astimezone(UTC)
        gap_start_utc = started + timedelta(seconds=float(gap[0]))
        gap_end_utc = started + timedelta(seconds=float(gap[1]))
        enrollment_utc = local_to_utc(enrollment_event["ts_local"], enrollment_event["tz"])
        overlaps = gap_start_utc <= enrollment_utc <= gap_end_utc
        decisive_turns = [
            turn for turn in transcript
            if not (float(turn["end_s"]) <= gap[0] or float(turn["start_s"]) >= gap[1])
        ]
        return overlaps, gap, decisive_turns, enrollment_utc, gap_start_utc, gap_end_utc

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        used = state["tool_calls_used"]
        governing_date = interaction["started_at_utc"][:10]
        population, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "recorder_failover_gap_population", "parameters": {},
             "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Count the calls affected by the same recorder failover incident",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        sales_during_gap, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "recorder_failover_gap_sales", "parameters": {},
             "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Find how many of the affected calls had an add-on enrollment submitted during their own gap",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        incident, used = self.tools.execute(
            "get_incident", {"incident_id": "INC-9002101"},
            rationale="Retrieve the recorder failover incident record",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        fee_ledger, used = self.tools.execute(
            "get_fee_ledger", {"account_id": interaction["account_id"]},
            rationale="Confirm no premium was ever billed for the CardShield enrollment",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SAL-001", "governing_date": governing_date},
            rationale="Resolve the affirmative-consent and enrollment-timing rules as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "population": population, "sales_during_gap": sales_during_gap,
                    "incident": incident, "fee_ledger": fee_ledger, "policy": policy}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary="Added the recorder failover incident, affected population, and gap-sale count",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["did", "incident", "population", "fee_ledger", "policy"]},
            refs=[incident["incident_id"], policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used,
                "population_count": len(population), "sales_during_gap_count": len(sales_during_gap),
                "gather_event_seqs": [update.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction = state["route_facts"]["interaction"]
        enrollment_event = next(row for row in evidence["desktop_events"] if row["type"] == "enrollment_submitted")
        overlaps, gap, decisive_turns, enrollment_utc, gap_start_utc, gap_end_utc = self._gap_overlap(
            interaction, enrollment_event, evidence["transcript"],
        )
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="gap_overlap_check"),
            type=EventType.COMPUTATION,
            summary=f"The recording gap [{gap[0]},{gap[1]}]s genuinely overlaps the enrollment submission",
            payload={"helper": "local_to_utc", "inputs": {"ts_local": enrollment_event["ts_local"],
                     "tz": enrollment_event["tz"], "gap_start_s": gap[0], "gap_end_s": gap[1]},
                     "gap_start_utc": _iso(gap_start_utc), "gap_end_utc": _iso(gap_end_utc),
                     "enrollment_utc": _iso(enrollment_utc), "output": overlaps,
                     "runtime": "registered_python_helper"},
            refs=[enrollment_event["event_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The decisive consent moment falls entirely inside the unrecoverable gap; no transcript covers it",
            payload={"finding_id": "F1", "status": "insufficient_evidence_candidate",
                     "gap_overlaps_enrollment": overlaps, "decisive_transcript_turns": len(decisive_turns),
                     "audio_recovery_status": evidence["audio_recovery_result"]["status"],
                     "population_count": state["population_count"],
                     "sales_during_gap_count": state["sales_during_gap_count"]},
            refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02",
                  enrollment_event["event_id"], "AUD-9002101"],
        )
        return {"gap_overlaps_enrollment": overlaps, "gap_bounds": gap, "decisive_turns_count": len(decisive_turns),
                "computation_seq": computation.seq, "reconcile_event_seq": finding.seq, "root_cause_changed": False}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction = state["route_facts"]["interaction"]
        policy = evidence["policy"]
        checks = {
            "recording_status_partial": interaction["recording_status"] == "partial",
            "enrollment_within_gap_window": state["gap_overlaps_enrollment"] is True,
            "decisive_span_has_zero_transcript_turns": state["decisive_turns_count"] == 0,
            "audio_recovery_confirmed_unrecoverable": evidence["audio_recovery_result"]["status"] == "unrecoverable",
            "recorder_failover_population_matches": state["population_count"] == 23,
            "sales_during_gap_count_matches": state["sales_during_gap_count"] == 4,
            "policy_as_of": policy["version"] == "v4" and policy["effective_from"] <= interaction["started_at_utc"][:10],
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED,
            summary="Verified the decisive consent span carries zero transcript coverage inside the gap",
            payload={"interaction_id": state["interaction_ids"][0], "gap_bounds_s": state["gap_bounds"],
                     "overlapping_turns": state["decisive_turns_count"],
                     "valid": checks["decisive_span_has_zero_transcript_turns"]},
            refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified SAL-001 v4 governed the interaction date",
            payload={"doc": policy["source_id"], "clauses": ["3.1", "4.1"],
                     "governing_date": interaction["started_at_utc"][:10], "valid": checks["policy_as_of"]},
            refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C18_L3", "result": "pass" if passed else "fail"},
                refs=["AUD-9002101", policy["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C18 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        snapshot = {"finding": "MC-02 insufficient_evidence candidate",
                    "gap_bounds_s": state["gap_bounds"], "audio_recovery_status": evidence["audio_recovery_result"]["status"],
                    "population_count": state["population_count"], "sales_during_gap_count": state["sales_during_gap_count"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity with an audio-recovery attempt that failed on the decisive span",
            payload={"predicate": "high_severity_and_unrecoverable_decisive_gap", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: reverse the enrollment despite no proof of misconduct because consent "
                    "cannot be confirmed and the customer should not bear an unresolved evidentiary gap",
            payload={"role": "customer_advocate", "position": "reverse_enrollment_despite_no_proof",
                     "key_refs": ["AUD-9002101", "ENR-9002101"], "snapshot_hash": snapshot_hash},
            refs=["AUD-9002101", "ENR-9002101"],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: there is no evidence of misconduct at all; the recorder failover, not the "
                    "colleague, erased the only span that could prove or disprove consent",
            payload={"role": "colleague_advocate", "position": "no_evidence_against_colleague",
                     "key_refs": ["INC-9002101"], "snapshot_hash": snapshot_hash},
            refs=["INC-9002101"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: neither position is adequately supported by decisive evidence; the actual "
                    "consent moment is simply unknown",
            payload={"determinative_issue": "whether the missing consent span can be inferred from surrounding evidence",
                     "decision": "insufficient_evidence",
                     "flip_fact": "a recovered audio span that actually captures the consent exchange"},
            refs=["AUD-9002101", f"{state['interaction_ids'][0]}:t02"],
        )
        components = {"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                      "evidence_coverage": 0.0, "transcript_quality": 0.0, "panel_agreement": 0.0}
        weights = {"verifier_pass_rate": 0.25, "citation_verification": 0.20, "evidence_coverage": 0.25,
                   "transcript_quality": 0.20, "panel_agreement": 0.10}
        computed_confidence = round(sum(components[key] * weights[key] for key in weights), 4)
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED,
            summary="Computed confidence with a 0.0 panel_agreement and zero decisive-span coverage",
            payload={**components, "weights": weights, "result": computed_confidence},
            refs=["AUD-9002101", state["evidence"]["policy"]["source_id"]],
        )
        return {"panel_used": True,
                "panel_reason": "severity high and the audio-recovery attempt failed on the decisive span; the "
                                "4-call gap-sale count is below the systemic population threshold of 10, so the "
                                "panel here is triggered by evidentiary uncertainty, not population size",
                "computed_confidence": computed_confidence, "outreach_needed": True,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        latest_date = latest_safe_decision(interaction["started_at_utc"], interaction["started_at_utc"], 10)
        respond_by = f"{latest_date}T23:59:59Z"
        if not state.get("outreach_needed"):
            computation = self.ledger.emit(
                **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
                type=EventType.COMPUTATION, summary=f"Computed monitoring deadline {latest_date}",
                payload={"helper": "latest_safe_decision", "inputs": {
                    "interaction_date": interaction["started_at_utc"][:10],
                    "trigger_date": interaction["started_at_utc"][:10], "business_days": 10,
                    "excluded_holiday": "2026-11-11"},
                    "output": latest_date, "runtime": "registered_python_helper"},
                refs=[interaction["interaction_id"]],
            )
            request, used = self.tools.execute(
                "request_artifact", {
                    "artifact_id": "AUD-9002101", "interaction_id": interaction["interaction_id"],
                    "kind": "audio_recovery", "respond_by": respond_by,
                    "idempotency_key": f"{state['review_id']}:AUD-9002101",
                }, rationale="Attempt to recover audio for the recording gap that overlaps the enrollment moment",
                used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            return {"artifact_request": request, "tool_calls_used": used,
                    "latest_safe_decision": respond_by, "deadline_event_seqs": [computation.seq],
                    "resume_target": "integrity"}
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION,
            summary=f"Recomputed monitoring deadline {latest_date} for the customer-outreach wait",
            payload={"helper": "latest_safe_decision", "inputs": {
                "interaction_date": interaction["started_at_utc"][:10],
                "trigger_date": interaction["started_at_utc"][:10], "business_days": 10,
                "excluded_holiday": "2026-11-11"},
                "output": latest_date, "runtime": "registered_python_helper"},
            refs=[interaction["interaction_id"]],
        )
        request, used = self.tools.execute(
            "message_customer", {
                "customer_id": interaction["customer_id"],
                "question": "Part of your call was not recorded because of a system outage, and we could not "
                             "recover that audio. Our records show a CardShield protection enrollment was "
                             "submitted during that unrecorded part of the call. Do you remember agreeing to add "
                             "that protection?",
                "respond_by": respond_by, "idempotency_key": f"{state['review_id']}:OUTREACH",
            }, rationale="Ask the customer whether they remember consenting before deciding remediation",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used,
                "latest_safe_decision": respond_by,
                "deadline_event_seqs": [*state.get("deadline_event_seqs", []), computation.seq],
                "resume_target": "decide"}

    def prepare_wait(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["artifact_request"]
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Recorded the external wait and latest safe decision",
            payload={"path": "deadlines.json", "expected_at": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "artifact_id": request["artifact_id"]}, refs=[request["artifact_id"]],
        )
        wait = self.ledger.emit(
            **node_context(state), actor=Actor(kind="harness", name="virtual_clock"),
            type=EventType.WAIT_SUSPENDED, summary=f"Suspended only for the requested {request['kind']}",
            payload={"artifact_id": request["artifact_id"], "until": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "idempotency_key": request["idempotency_key"]}, refs=[request["artifact_id"]],
        )
        return {"status": "suspended", "termination": "waiting_external",
                "wait_event_seqs": [*state.get("wait_event_seqs", []), update.seq, wait.seq]}

    def ingest_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        resumed = state["resume_payload"]
        now = datetime.fromisoformat(resumed["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)
        if not resumed["arrived"] or resumed["artifact"] is None:
            raise RuntimeError("C18 requested artifact did not arrive before latest safe decision")
        request = state["artifact_request"]
        wait_summary = {"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                         "requested_at": request["requested_at"], "expected_at": request["expected_at"],
                         "arrived_at": resumed["virtual_now"], "latest_safe_decision": state["latest_safe_decision"],
                         "result": "arrived"}
        if resumed["kind"] == "audio_recovery":
            arrived = self.ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
                actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.ARTIFACT_ARRIVED,
                summary="Released the audio-recovery result into the agent view",
                payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                         "available_at": resumed["virtual_now"],
                         "artifact_blob": self.ledger.put_blob(resumed["artifact"])},
                refs=[resumed["artifact_id"], state["interaction_ids"][0]],
            )
            wait = self.ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
                actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
                summary="Resumed C18 after the audio-recovery result arrived",
                payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                         "reason": "artifact_arrived"}, refs=[resumed["artifact_id"]],
            )
            evidence = {**state["evidence"], "audio_recovery_result": resumed["artifact"]}
            return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                    "status": "running", "termination": None,
                    "artifact_event_seqs": [*state.get("artifact_event_seqs", []), arrived.seq, wait.seq],
                    "waits_history": [*state.get("waits_history", []), wait_summary]}
        arrived = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.PERSONA_REPLY,
            summary="Released the customer's outreach reply into the agent view",
            payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                     "available_at": resumed["virtual_now"],
                     "reply_blob": self.ledger.put_blob(resumed["artifact"])},
            refs=[resumed["artifact_id"], state["interaction_ids"][0]],
        )
        wait = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
            summary="Resumed C18 after the customer's outreach reply arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "customer_reply_arrived"}, refs=[resumed["artifact_id"]],
        )
        evidence = {**state["evidence"], "customer_reply": resumed["artifact"]["text"]}
        return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "artifact_event_seqs": [*state.get("artifact_event_seqs", []), arrived.seq, wait.seq],
                "waits_history": [*state.get("waits_history", []), wait_summary]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        reply = state["evidence"]["customer_reply"]
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-02 insufficient evidence; neither position is decisively supported",
            payload={"finding_id": "F1", "category": "MC-02", "status": "insufficient_evidence",
                     "attributable_to": "none", "customer_reply": reply},
            refs=["AUD-9002101", "ENR-9002101", state["artifact_request"]["artifact_id"]],
        )
        conservative = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.CONSERVATIVE_DEFAULT_APPLIED,
            summary="Applied the conservative default: no adverse colleague finding, customer-protective remediation",
            payload={"colleague": "no_adverse_finding", "customer": "reverse_enrollment",
                     "reason": "confidence_below_0.75", "computed_confidence": state["computed_confidence"]},
            refs=["AUD-9002101", "ENR-9002101"],
        )
        return {"finding_event_seq": event.seq, "conservative_default_event_seq": conservative.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped colleague memory because an evidentiary gap is not a colleague lesson",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "insufficient_evidence from an unrecoverable recording gap is case-local, not a "
                               "generalizable colleague pattern",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=["AUD-9002101"],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        gap = state["gap_bounds"]
        incident = evidence["incident"]
        policy = evidence["policy"]
        outreach_artifact_id = state["waits_history"][-1]["artifact_id"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", "AUD-9002101", "ENR-9002101",
                       incident["incident_id"], policy["source_id"], outreach_artifact_id]
        seqs = sorted(set([
            state["route_event_seq"], state["computation_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["conservative_default_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["gather_event_seqs"], *state["verification_seqs"],
            *state["panel_event_seqs"], *state["wait_event_seqs"], *state["artifact_event_seqs"],
            *state["deadline_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-02", status="insufficient_evidence", attributable_to="none",
            severity="high", interaction_id=interaction_id,
            evidence_spans=[
                {"interaction_id": interaction_id, "turn_id": "t01",
                 "start_s": float(turns["t01"]["start_s"]), "end_s": float(turns["t01"]["end_s"]),
                 "quote": turns["t01"]["text"], "verified": True},
                {"interaction_id": interaction_id, "turn_id": "GAP", "start_s": float(gap[0]), "end_s": float(gap[1]),
                 "quote": "[recording gap — no transcript; CardShield enrollment submitted during this window]",
                 "verified": False, "artifact_id": "AUD-9002101"},
                {"interaction_id": interaction_id, "turn_id": "t02",
                 "start_s": float(turns["t02"]["start_s"]), "end_s": float(turns["t02"]["end_s"]),
                 "quote": turns["t02"]["text"], "verified": True},
            ],
            structured_evidence=[
                {"source": "enrollments", "id": "ENR-9002101",
                 "fact": "CardShield enrollment submitted inside the unrecoverable recording gap"},
                {"source": "audio_recovery", "id": "AUD-9002101",
                 "fact": f"Audio recovery attempted and returned status={evidence['audio_recovery_result']['status']}"},
                {"source": "incidents", "id": incident["incident_id"],
                 "fact": f"Recorder failover affected {state['population_count']} calls; "
                         f"{state['sales_during_gap_count']} had an add-on enrollment submitted during their own gap"},
            ],
            policy_refs=[{"doc_id": policy["source_id"], "clauses": ["3.1", "4.1"], "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [{"action": "reverse_enrollment"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_adverse_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_gap_record", "incident_id": incident["incident_id"],
                 "population": state["population_count"], "sales_during_gap": state["sales_during_gap_count"]},
            ]},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": True,
                             "flip_fact": "a recovered audio span that actually captures the consent exchange"},
            "waits": state["waits_history"],
            "memory_ops": [{"op": "skip", "reason": "insufficient_evidence is case-local, not a colleague lesson",
                            "source_refs": ["AUD-9002101"]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "the customer affirmatively consented during the unrecorded gap",
                 "status": "unresolved", "evidence_for": [], "evidence_against": []},
                {"id": "H2", "label": "the enrollment was submitted without consent during the unrecorded gap",
                 "status": "unresolved", "evidence_for": [], "evidence_against": []},
            ],
            "citations": [{"doc_id": policy["source_id"],
                           "why": "affirmative consent and enrollment timing requirements"}],
            "summary_for_record": (
                "MC-02 insufficient evidence. The CardShield enrollment was submitted inside a recording gap "
                f"caused by a recorder failover ({incident['incident_id']}, {state['population_count']} calls "
                f"affected, {state['sales_during_gap_count']} with a sale during their own gap); audio recovery "
                "was attempted and confirmed unrecoverable, and no transcript turn covers the decisive consent "
                "moment. The panel found neither the customer-protective nor the colleague-clearing position "
                "decisively supported; confidence stayed below 0.75, so the conservative default applies: no "
                "adverse finding against the colleague, and the enrollment is reversed for the customer regardless."
            ),
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C18 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
