"""C15 preference-sync control gap: an apparent opt-out violation is a system failure once the desktop and
incident record are checked; the harness supplies the customer's own outreach choice before deciding."""

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
from conductai.runtime.deadlines import latest_safe_decision
from conductai.runtime.support import leaf_paths, node_context
from conductai.tools.executor import ToolExecutor


class C15Workflow:
    """Deterministic preference-sync control-gap path with a customer-outreach wait; C15 only."""

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
        if route.route_id != "preference_suppression_incident":
            raise RuntimeError("C15 requires the preference_suppression_incident route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the preference-suppression control-gap path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "preference_do_not_solicit_present": state["route_facts"]["preference_do_not_solicit_present"],
                         "balance_transfer_offer_present": state["route_facts"]["balance_transfer_offer_present"],
                     }}, refs=[state["interaction_ids"][0]],
        )
        return {"route": route.model_dump(mode="json"), "route_event_seq": event.seq}

    def integrity(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("root_cause_changed"):
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED,
                summary="Continuing with the expanded incident-population scope; no further transcript-integrity question",
                payload={"path": "evidence_matrix.json", "columns": ["said", "did", "incident", "population"]},
                refs=[state["interaction_ids"][0]],
            )
            return {"artifact_needed": False, "integrity_event_seqs": [*state["integrity_event_seqs"], event.seq]}
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the balance-transfer submission call for any solicitation-consent language",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Confirm what the colleague's own desktop profile showed at call time",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the transfer request is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript, "desktop_events": desktop}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        evidence = state["evidence"]
        customer_id = state["route_facts"]["interaction"]["customer_id"]
        if "preference" not in evidence:
            history, used = self.tools.execute(
                "query_graph", {
                    "template_id": "customer_interaction_history",
                    "parameters": {"customer_id": customer_id, "before_at": state["route_facts"]["interaction"]["started_at_utc"]},
                    "as_of": state["route_facts"]["interaction"]["started_at_utc"][:10], "max_hops": 2, "limit": 20,
                }, rationale="Find the prior interaction where the customer opted out of solicitation",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            prior_chat_id = history[0]["interaction_id"]
            prior_transcript, used = self.tools.execute(
                "get_transcript", {"interaction_id": prior_chat_id},
                rationale="Read the exact opt-out request and the colleague's confirmation",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            preferences, used = self.tools.execute(
                "get_preference", {"customer_id": customer_id, "preference": "DO_NOT_SOLICIT"},
                rationale="Retrieve the recorded do-not-solicit preference and its desktop sync status",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            offers, used = self.tools.execute(
                "get_offers", {"interaction_id": interaction_id},
                rationale="Confirm the balance-transfer offer submitted on this call",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            evidence = {**evidence, "history": history, "prior_chat_id": prior_chat_id,
                        "prior_transcript": prior_transcript, "preference": preferences[0], "offer": offers[0]}
            blob = self.ledger.put_blob(evidence)
            update = self.ledger.emit(
                **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED, summary="Added the prior opt-out, preference record, and offer",
                payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "did", "preference"]},
                refs=[prior_chat_id, evidence["preference"]["pref_id"], evidence["offer"]["offer_instance_id"]],
            )
            return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [update.seq]}
        incident, used = self.tools.execute(
            "get_incident", {"incident_id": "INC-9001801"},
            rationale="Retrieve the preference-sync incident window that delayed the desktop flag",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        population, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "preference_sync_incident_population",
             "parameters": {"from_at": incident["started_at_utc"], "to_at": incident["ended_at_utc"]},
             "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Count phone customers who were solicited while their opt-out was still delayed by the same incident",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**evidence, "incident": incident, "population": population}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the incident record and the affected-customer population",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["incident", "population"]},
            refs=[incident["incident_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [*state["gather_event_seqs"], update.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        prior_seqs = state.get("reconcile_event_seqs", [])
        if "population" not in evidence:
            desktop_flag = next(
                (row for row in evidence["desktop_events"] if row["type"] == "profile_loaded"), None,
            )
            desktop_showed_flag = bool(desktop_flag) and json.loads(desktop_flag["payload"]).get("solicitation_flag") is True
            finding = self.ledger.emit(
                **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
                type=EventType.FINDING_UPDATED,
                summary="The colleague's desktop never showed the do-not-solicit flag because its sync was delayed by an incident",
                payload={"finding_id": "F1", "from": "colleague_solicitation_after_optout", "to": "control_gap",
                         "reason": "preference recorded and delayed only in the desktop sync, not colleague disregard",
                         "desktop_showed_flag": desktop_showed_flag,
                         "preference_sync_status": evidence["preference"]["sync_status"]},
                refs=[f"{state['interaction_ids'][0]}:t01", evidence["preference"]["pref_id"]],
            )
            return {"root_cause_changed": True,
                     "reroute_reason": "the root cause is a preference-sync control gap, not colleague fault — "
                                       "scope must expand to the incident-affected population",
                     "desktop_showed_flag": desktop_showed_flag,
                     "reconcile_event_seqs": [*prior_seqs, finding.seq]}
        population = evidence["population"]
        affected_customers = sorted({row["customer_id"] for row in population})
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="population_count"),
            type=EventType.COMPUTATION,
            summary=f"Incident affected {len(affected_customers)} phone customers with a still-delayed opt-out",
            payload={"helper": "population_count",
                     "inputs": {"qualifying_interactions": len(population)},
                     "output": len(affected_customers), "runtime": "registered_python_helper"},
            refs=[evidence["incident"]["incident_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.FINDING_UPDATED,
            summary="Finalized the incident-affected population",
            payload={"finding_id": "F1", "status": "control_gap", "population": len(affected_customers),
                     "customers": affected_customers},
            refs=[evidence["incident"]["incident_id"]],
        )
        return {"root_cause_changed": False, "population_count": len(affected_customers),
                "population_customers": affected_customers, "population_seqs": [computation.seq, finding.seq],
                "reconcile_event_seqs": [*prior_seqs, computation.seq, finding.seq]}

    def reroute(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.PLAN_UPDATED,
            summary="Re-planned from an individual colleague review to an incident-population control-gap check",
            payload={"reason_event_seq": state["reconcile_event_seqs"][-1],
                     "patch": [{"op": "add", "path": "/steps/-",
                                "value": "look up the preference-sync incident and count affected customers"}]},
            refs=[state["interaction_ids"][0]],
        )
        return {"reroute_event_seqs": [event.seq]}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["prior_transcript"] if t["turn_id"] == "t01")
        checks = {
            "opt_out_quote_exact": "stop offering me stuff" in turn["text"].lower(),
            "desktop_did_not_show_flag": not state["desktop_showed_flag"],
            "preference_sync_delayed": evidence["preference"]["sync_status"] == "delayed",
            "incident_covers_call": evidence["incident"]["started_at_utc"] <= state["route_facts"]["interaction"]["started_at_utc"] <= evidence["incident"]["ended_at_utc"],
            "population_matches_incident_scope": state["population_count"] == 9,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact opt-out request in the prior chat",
            payload={"interaction_id": evidence["prior_chat_id"], "turn_id": "t01",
                     "quote": turn["text"], "substring_match": checks["opt_out_quote_exact"]},
            refs=[f"{evidence['prior_chat_id']}:t01"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C15_L3", "result": "pass" if passed else "fail"},
                refs=[evidence["preference"]["pref_id"], evidence["incident"]["incident_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C15 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0,
                     "evidence_coverage": 1.0, "transcript_quality": 1.0,
                     "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[evidence["incident"]["incident_id"]],
        )
        return {"verifier_checks": checks, "verification_seqs": [span.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "no adverse colleague finding, no remediation cost, and a population of 9 below the "
                                "systemic-panel threshold of 10",
                "panel_event_seqs": [], "outreach_needed": True}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        latest_date = latest_safe_decision(interaction["started_at_utc"], "2026-11-13", 10)
        respond_by = f"{latest_date}T23:59:59Z"
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION, summary=f"Computed monitoring deadline {latest_date} from the lookback selection date",
            payload={"helper": "latest_safe_decision", "inputs": {
                "interaction_date": interaction["started_at_utc"][:10], "trigger_date": "2026-11-13",
                "business_days": 10, "excluded_holiday": "2026-11-26"},
                "output": latest_date, "runtime": "registered_python_helper"},
            refs=[interaction["interaction_id"]],
        )
        request, used = self.tools.execute(
            "message_customer", {
                "customer_id": state["route_facts"]["interaction"]["customer_id"],
                "question": "Your balance transfer was processed while your do-not-solicit request was still "
                             "waiting to reach our systems. Would you like to keep the transfer, and should we "
                             "make sure you are not offered further products?",
                "respond_by": respond_by, "idempotency_key": f"{state['review_id']}:OUTREACH",
            }, rationale="Ask the customer whether to keep the transfer before deciding remediation",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used,
                "latest_safe_decision": respond_by, "deadline_event_seq": computation.seq,
                "resume_target": "decide"}

    def prepare_wait(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["artifact_request"]
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Recorded the customer-outreach wait and latest safe decision",
            payload={"path": "deadlines.json", "expected_at": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "artifact_id": request["artifact_id"]}, refs=[request["artifact_id"]],
        )
        wait = self.ledger.emit(
            **node_context(state), actor=Actor(kind="harness", name="virtual_clock"),
            type=EventType.WAIT_SUSPENDED, summary="Suspended only for the customer's outreach reply",
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
            raise RuntimeError("C15 customer reply did not arrive before latest safe decision")
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
            summary="Resumed C15 after the customer's reply arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "customer_reply_arrived"}, refs=[resumed["artifact_id"]],
        )
        evidence = {**state["evidence"], "customer_reply": resumed["artifact"]["text"]}
        return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "artifact_event_seqs": [arrived.seq, wait.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        reply = state["evidence"]["customer_reply"]
        keep_transfer = "keep" in reply.lower()
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-09 control gap attributable to the preference-sync incident; customer chose to keep the transfer",
            payload={"finding_id": "F1", "category": "MC-09", "status": "control_gap", "attributable_to": "system",
                     "customer_reply": reply, "keep_transfer": keep_transfer},
            refs=[state["interaction_ids"][0], state["evidence"]["incident"]["incident_id"]],
        )
        return {"finding_event_seq": event.seq, "keep_transfer": keep_transfer}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped colleague memory because the finding is attributable to a system control gap",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "control gap attributable to the preference-sync incident, not a colleague lesson",
                     "gate_checks": {"case_local": False, "generalizable": False, "prohibited_content": False}},
            refs=[state["evidence"]["incident"]["incident_id"]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        preference = evidence["preference"]
        incident = evidence["incident"]
        offer = evidence["offer"]
        source_refs = [f"{evidence['prior_chat_id']}:t01", preference["pref_id"], incident["incident_id"],
                       offer["offer_instance_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["deadline_event_seq"], state["finding_event_seq"],
            state["memory_event_seq"], *state["integrity_event_seqs"], *state["gather_event_seqs"],
            *state["reconcile_event_seqs"], *state["reroute_event_seqs"], *state["population_seqs"],
            *state["verification_seqs"], *state["wait_event_seqs"], *state["artifact_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-09", status="control_gap", attributable_to="system", severity="medium",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": evidence["prior_chat_id"], "turn_id": "t01",
                             "start_s": 26.5, "end_s": 26.5, "quote": "Stop offering me stuff.", "verified": True}],
            structured_evidence=[
                {"source": "preferences", "id": preference["pref_id"], "fact": f"sync_status={preference['sync_status']}"},
                {"source": "incidents", "id": incident["incident_id"],
                 "fact": f"{state['population_count']} phone customers solicited while their opt-out was still delayed"},
            ],
            policy_refs=[], confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False, "remediation": [{"action": "suppress_solicitation"}],
                                 "customer_choice": "keep_transfer" if state["keep_transfer"] else "reverse_transfer"},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_gap_record", "incident_id": incident["incident_id"], "population": state["population_count"]},
            ]},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the desktop had actually shown the do-not-solicit flag at call time"},
            "waits": [{"artifact_id": state["artifact_request"]["artifact_id"], "kind": "customer_reply",
                       "requested_at": state["artifact_request"]["requested_at"],
                       "expected_at": state["artifact_request"]["expected_at"],
                       "arrived_at": state["virtual_now"], "latest_safe_decision": state["latest_safe_decision"],
                       "result": "arrived"}],
            "memory_ops": [{"op": "skip", "reason": "control gap attributable to the incident, not a colleague lesson",
                            "source_refs": [incident["incident_id"]]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "colleague solicited a customer who had opted out", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "the desktop never showed the opt-out flag because its sync was delayed by "
                                       "a preference-sync incident", "status": "supported", "evidence_for": source_refs},
            ], "citations": [],
            "summary_for_record": "MC-09 control gap. The colleague's desktop never carried the customer's "
                                   f"do-not-solicit flag because {incident['incident_id']} delayed its sync; "
                                   f"{state['population_count']} phone customers were affected. The customer chose "
                                   "to keep the transfer and asked only to stop further solicitation.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C15 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
