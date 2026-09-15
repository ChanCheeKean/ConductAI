"""C01 transcript-integrity investigation with external-artifact wait/resume."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.contracts import LeadReviewer, LeadReviewRequest
from conductai.runtime.deadlines import latest_safe_decision
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C01Workflow:
    def __init__(
        self, root: Path, config: ResolvedConfig, tools: ToolExecutor,
        ledger: EventLedger, lead: LeadReviewer,
    ) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger
        self.lead = lead

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=20, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "addon_consent_integrity":
            raise RuntimeError("C01 requires the addon_consent_integrity route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected add-on consent L2 integrity path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "addon_enrollment_present": state["route_facts"]["addon_enrollment_present"],
                         "transcript_integrity_review_needed": state["route_facts"]["transcript_integrity_review_needed"],
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
        if state.get("artifact") is not None:
            return self._assess_retranscription(state)
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Inspect the decisive consent span with word and channel metadata",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollments, used = self.tools.execute(
            "get_enrollments", {"interaction_id": interaction_id},
            rationale="Confirm the add-on enrollment that makes the consent span decision-changing",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Align the enrollment submission with the spoken consent sequence",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        decisive = next(turn for turn in transcript if turn["turn_id"] == "t03")
        word_quality = {word["w"]: float(word["conf"]) for word in decisive["words"]}
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED, summary="Found low-confidence polarity words in decisive consent span",
            payload={"interaction_id": interaction_id, "turn_id": "t03", "source": "asr",
                     "word_confidence": word_quality, "minimum_decisive_quality": min(word_quality.values()),
                     "speaker_channel_match": decisive["speaker"] == decisive["speaker_channel"],
                     "recovery_recommended": "retranscription"},
            refs=[f"{interaction_id}:t03"],
        )
        evidence = {"transcript": transcript, "enrollments": enrollments, "desktop_events": desktop,
                    "asr_decisive_turn": decisive}
        lead_decision = self.lead.investigate(
            LeadReviewRequest(
                review_id=state["review_id"], interaction_id=interaction_id,
                route_id=state["route"]["route_id"],
                open_question="Did the customer affirmatively consent, or did ASR invert the decisive span?",
                evidence={"decisive_text": decisive["text"], "word confidence": word_quality,
                          "enrollment": enrollments[0], "desktop_event": desktop[0]},
            ), run_id=state["run_id"], review_id=state["review_id"], virtual_now=state["virtual_now"],
        )
        if lead_decision.next_action != "request_retranscription":
            raise RuntimeError("C01 lead failed to request decision-changing evidence")
        plan = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.PLAN_CREATED, summary="Created bounded C01 integrity plan",
            payload={**lead_decision.model_dump(mode="json"), "max_replans": state["route"]["budget"]["replans"]},
            refs=[interaction_id, enrollments[0]["enrollment_id"]],
        )
        hypotheses = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.HYPOTHESIS_UPDATED, summary="Opened unauthorized-enrollment and ASR-error hypotheses",
            payload={"hypotheses": lead_decision.hypotheses, "reason": "decisive low-confidence polarity"},
            refs=[f"{interaction_id}:t03", enrollments[0]["enrollment_id"]],
        )
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added C01 said/did evidence and open hypotheses",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["said", "did", "recorded"]},
            refs=[f"{interaction_id}:t02", f"{interaction_id}:t03",
                  enrollments[0]["enrollment_id"], desktop[0]["event_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "artifact_needed": True,
                "plan": lead_decision.plan, "plan_event_seq": plan.seq,
                "hypothesis_event_seqs": [hypotheses.seq], "integrity_event_seqs": [assessed.seq]}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        trigger_at = state["route_facts"]["scanner_flags"][0]["flagged_at"]
        latest_date = latest_safe_decision(interaction["started_at_utc"], trigger_at)
        respond_by = f"{latest_date}T23:59:59Z"
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION, summary=f"Computed monitoring deadline {latest_date}",
            payload={"helper": "latest_safe_decision", "inputs": {
                "interaction_date": interaction["started_at_utc"][:10], "trigger_date": trigger_at[:10],
                "business_days": 10, "excluded_holiday": "2026-11-26"},
                "output": latest_date, "runtime": "registered_python_helper"},
            refs=[state["trigger"]["id"], interaction["interaction_id"]],
        )
        request, used = self.tools.execute(
            "request_artifact", {
                "artifact_id": "RTX-9000101", "interaction_id": interaction["interaction_id"],
                "kind": "retranscription", "respond_by": respond_by,
                "idempotency_key": f"{state['review_id']}:RTX-9000101",
            }, rationale="Resolve the outcome-changing low-confidence consent span before the SLA",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used,
                "latest_safe_decision": respond_by, "deadline_event_seq": computation.seq}

    def prepare_wait(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["artifact_request"]
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Recorded external wait and latest safe decision",
            payload={"path": "deadlines.json", "expected_at": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "artifact_id": request["artifact_id"]}, refs=[request["artifact_id"]],
        )
        wait = self.ledger.emit(
            **node_context(state), actor=Actor(kind="harness", name="virtual_clock"),
            type=EventType.WAIT_SUSPENDED, summary="Suspended only for the requested re-transcription",
            payload={"artifact_id": request["artifact_id"], "until": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "idempotency_key": request["idempotency_key"]}, refs=[request["artifact_id"]],
        )
        return {"status": "suspended", "termination": "waiting_external",
                "wait_event_seqs": [update.seq, wait.seq]}

    def ingest_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        resumed = state["resume_payload"]
        now = datetime.fromisoformat(resumed["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)
        if not resumed["arrived"] or resumed["artifact"] is None:
            raise RuntimeError("C01 re-transcription did not arrive before latest safe decision")
        arrived = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.ARTIFACT_ARRIVED,
            summary="Released requested re-transcription into the agent view",
            payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                     "available_at": resumed["virtual_now"],
                     "artifact_blob": self.ledger.put_blob(resumed["artifact"])},
            refs=[resumed["artifact_id"], state["interaction_ids"][0]],
        )
        wait = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
            summary="Resumed C01 after the requested artifact arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "artifact_arrived"}, refs=[resumed["artifact_id"]],
        )
        return {"artifact": resumed["artifact"], "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "artifact_event_seqs": [arrived.seq, wait.seq]}

    def _assess_retranscription(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        recovered = state["artifact"]["turns"][0]
        recovered_quality = min(float(word["conf"]) for word in recovered["words"])
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED, summary="Higher-fidelity channel-separated span resolved consent",
            payload={"interaction_id": interaction_id, "turn_id": recovered["turn_id"],
                     "source": "retranscription", "method": state["artifact"]["method"],
                     "minimum_decisive_quality": recovered_quality,
                     "recovery_recommended": None},
            refs=["RTX-9000101", f"{interaction_id}:{recovered['turn_id']}"],
        )
        contradiction = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.CONTRADICTION_DETECTED, summary="Re-transcription reversed the ASR consent polarity",
            payload={"claim_a": state["evidence"]["asr_decisive_turn"]["text"],
                     "claim_b": recovered["text"], "resolution": "prefer channel-separated human-verified artifact"},
            refs=[f"{interaction_id}:t03", "RTX-9000101"],
        )
        hypothesis = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.HYPOTHESIS_UPDATED, summary="Supported ASR-error hypothesis and rejected unauthorized enrollment",
            payload={"hypotheses": [
                {"id": "H1", "status": "rejected", "reason": "recovered affirmative consent"},
                {"id": "H2", "status": "supported", "reason": "human-verified re-transcription"},
            ]}, refs=["RTX-9000101", f"{interaction_id}:t03"],
        )
        evidence = {**state["evidence"], "retranscription": state["artifact"], "decisive_turn": recovered}
        return {"evidence": evidence, "artifact_needed": False,
                "recovered_transcript_quality": recovered_quality,
                "integrity_event_seqs": [*state["integrity_event_seqs"], assessed.seq, contradiction.seq],
                "hypothesis_event_seqs": [*state["hypothesis_event_seqs"], hypothesis.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SAL-001", "governing_date": governing_date},
            rationale="Resolve affirmative-consent and disclosure-order rules as of the interaction date",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "policy": policy}
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Completed C01 said/did/recorded/policy matrix",
            payload={"path": "evidence_matrix.json", "columns": ["said", "did", "recorded", "policy"]},
            refs=["RTX-9000101", state["evidence"]["enrollments"][0]["enrollment_id"], policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        enrollment = state["evidence"]["enrollments"][0]
        desktop = state["evidence"]["desktop_events"][0]
        interaction = state["route_facts"]["interaction"]
        desktop_utc = datetime.fromisoformat(desktop["ts_local"]).replace(
            tzinfo=ZoneInfo(desktop["tz"])
        ).astimezone(UTC)
        started = datetime.fromisoformat(interaction["started_at_utc"].replace("Z", "+00:00"))
        desktop_offset_s = (desktop_utc - started).total_seconds()
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED, summary="Reconciled affirmative consent, prior price disclosure, and in-call enrollment",
            payload={"finding_id": "F1", "status": "no_error_candidate",
                     "consent_before_enrollment": True, "price_before_consent": True,
                     "enrollment_during_interaction": True, "desktop_offset_s": desktop_offset_s},
            refs=["RTX-9000101", f"{state['interaction_ids'][0]}:t02", enrollment["enrollment_id"]],
        )
        return {"reconcile_event_seq": event.seq, "desktop_offset_s": desktop_offset_s}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        recovered = evidence["decisive_turn"]
        policy = evidence["policy"]
        checks = {
            "retranscription_affirmative": "I do need that" in recovered["text"] and "Go ahead" in recovered["text"],
            "price_preceded_consent": float(next(t for t in evidence["transcript"] if t["turn_id"] == "t02")["end_s"]) < float(recovered["start_s"]),
            "enrollment_followed_consent": (
                float(recovered["end_s"]) < state["desktop_offset_s"]
                <= (datetime.fromisoformat(state["route_facts"]["interaction"]["ended_at_utc"].replace("Z", "+00:00"))
                    - datetime.fromisoformat(state["route_facts"]["interaction"]["started_at_utc"].replace("Z", "+00:00"))).total_seconds()
            ),
            "policy_as_of": policy["version"] == "v4",
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified recovered affirmative-consent span",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": recovered["turn_id"],
                     "quote": recovered["text"], "artifact_id": "RTX-9000101", "valid": checks["retranscription_affirmative"]},
            refs=["RTX-9000101", f"{state['interaction_ids'][0]}:t03"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified SAL-001 v4 governed consent and disclosure order",
            payload={"doc": policy["source_id"], "clauses": ["3.1", "3.2", "4.1"],
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": checks["policy_as_of"]}, refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C01_L2", "result": "pass" if passed else "fail"},
                refs=["RTX-9000101", policy["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C01 deterministic verifier failed")
        computed_confidence = round(0.25 + 0.20 + 0.25 + 0.20 * state["recovered_transcript_quality"] + 0.10, 4)
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence after decisive-span recovery",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": state["recovered_transcript_quality"],
                     "panel_agreement": None, "nonpanel_consistency": 1.0,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20,
                                 "nonpanel_consistency": 0.10},
                     "result": computed_confidence},
            refs=["RTX-9000101", policy["source_id"]],
        )
        return {"verifier_checks": checks,
                "verification_seqs": [span.seq, citation.seq, *check_seqs, confidence.seq],
                "computed_confidence": computed_confidence}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False, "panel_reason": "no adverse finding or high-impact trigger"}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED, summary="Proposed no error after recovered affirmative consent",
            payload={"finding_id": "F1", "category": "none", "status": "no_error",
                     "attributable_to": "none"},
            refs=["RTX-9000101", state["evidence"]["enrollments"][0]["enrollment_id"],
                  state["evidence"]["policy"]["source_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped colleague memory because the scanner alert was a cleared ASR error",
            payload={"subject": state["route_facts"]["interaction"]["interaction_id"],
                     "reason": "cleared ASR artifact is case-local and not a colleague lesson",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=["RTX-9000101"],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction_id = state["interaction_ids"][0]
        enrollment = evidence["enrollments"][0]
        policy = evidence["policy"]
        source_refs = [f"{interaction_id}:t02", f"{interaction_id}:t03", "RTX-9000101",
                       enrollment["enrollment_id"], evidence["desktop_events"][0]["event_id"], policy["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["plan_event_seq"], state["deadline_event_seq"],
            state["reconcile_event_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["wait_event_seqs"], *state["artifact_event_seqs"],
            *state["integrity_event_seqs"], *state["hypothesis_event_seqs"], *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t03",
                             "start_s": float(evidence["decisive_turn"]["start_s"]),
                             "end_s": float(evidence["decisive_turn"]["end_s"]),
                             "quote": evidence["decisive_turn"]["text"], "verified": True,
                             "artifact_id": "RTX-9000101"}],
            structured_evidence=[{"source": "enrollments", "id": enrollment["enrollment_id"],
                                  "fact": "CardShield enrollment submitted during the call after consent"}],
            policy_refs=[{"doc_id": policy["source_id"], "clauses": ["3.1", "3.2", "4.1"], "verified": True}],
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
                             "flip_fact": "recovered evidence showing no affirmative consent"},
            "waits": [{"artifact_id": "RTX-9000101", "kind": "retranscription",
                       "requested_at": state["artifact_request"]["requested_at"],
                       "expected_at": state["artifact_request"]["expected_at"],
                       "arrived_at": state["virtual_now"], "latest_safe_decision": state["latest_safe_decision"],
                       "result": "arrived"}],
            "memory_ops": [{"op": "skip", "reason": "cleared ASR error is not a colleague lesson",
                            "source_refs": ["RTX-9000101"]}],
            "graph_writes": [],
            "hypotheses": [
                {"id": "H1", "label": "enrolled without affirmative consent", "status": "rejected",
                 "evidence_against": ["RTX-9000101"]},
                {"id": "H2", "label": "decisive negative is an ASR error", "status": "supported",
                 "evidence_for": ["RTX-9000101"]},
            ],
            "citations": [{"doc_id": policy["source_id"], "why": "affirmative consent and disclosure order"}],
            "summary_for_record": "No error. Higher-fidelity re-transcription confirms affirmative consent after price disclosure and before enrollment.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {
            path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths
        }
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C01 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
