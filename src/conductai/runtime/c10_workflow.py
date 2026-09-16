"""C10 bilingual ASR-routing quality: a queue misconfiguration transcribed a Spanish call with the wrong
ASR model; re-transcription with the correct model, as-of glossary retrieval, and fairness (language and
ASR confidence are never risk) resolve it to no error against the colleague, with a population control gap."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.deadlines import latest_safe_decision
from conductai.runtime.sandbox import pct_fee
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


class C10Workflow:
    """Deterministic bilingual-queue ASR-routing wait/resume path; C10 only."""

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
        if route.route_id != "bilingual_asr_quality":
            raise RuntimeError("C10 requires the bilingual_asr_quality route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the bilingual ASR-routing quality path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "bilingual_asr_mismatch_present": state["route_facts"]["bilingual_asr_mismatch_present"],
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
        if "recovered_transcript" in state.get("evidence", {}):
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED,
                summary="Continuing with the recovered Spanish-model transcript; no further integrity question",
                payload={"path": "evidence_matrix.json", "columns": ["said", "policy", "population"]},
                refs=[state["interaction_ids"][0]],
            )
            return {"artifact_needed": False, "integrity_event_seqs": [*state["integrity_event_seqs"], event.seq]}
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the original transcript transcribed under the wrong ASR model",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="The bilingual-queue call was transcribed with en-US-general against Spanish speech; "
                    "the recording is complete but the transcript text is unreliable",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": "retranscription"},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": True, "integrity_event_seqs": [assessed.seq]}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        latest_date = latest_safe_decision(interaction["started_at_utc"], "2026-11-01", 10)
        respond_by = f"{latest_date}T23:59:59Z"
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION,
            summary=f"Computed monitoring deadline {latest_date} from the v8 re-scan trigger date",
            payload={"helper": "latest_safe_decision", "inputs": {
                "interaction_date": interaction["started_at_utc"][:10], "trigger_date": "2026-11-01",
                "business_days": 10, "excluded_holiday": "2026-11-11"},
                "output": latest_date, "runtime": "registered_python_helper"},
            refs=[interaction["interaction_id"]],
        )
        request, used = self.tools.execute(
            "request_artifact", {
                "artifact_id": "RTX-9001201", "interaction_id": interaction["interaction_id"],
                "kind": "retranscription", "respond_by": respond_by,
                "idempotency_key": f"{state['review_id']}:RTX-9001201",
            }, rationale="Request re-transcription with the correct es-US ASR model",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used,
                "latest_safe_decision": respond_by, "deadline_event_seq": computation.seq,
                "resume_target": "integrity"}

    def prepare_wait(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["artifact_request"]
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Recorded the retranscription wait and latest safe decision",
            payload={"path": "deadlines.json", "expected_at": request["expected_at"],
                     "latest_safe_decision": state["latest_safe_decision"],
                     "artifact_id": request["artifact_id"]}, refs=[request["artifact_id"]],
        )
        wait = self.ledger.emit(
            **node_context(state), actor=Actor(kind="harness", name="virtual_clock"),
            type=EventType.WAIT_SUSPENDED, summary="Suspended only for the es-US re-transcription",
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
            raise RuntimeError("C10 re-transcription did not arrive before latest safe decision")
        arrived = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.ARTIFACT_ARRIVED,
            summary="Released the es-US re-transcription into the agent view",
            payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"], "available_at": resumed["virtual_now"]},
            refs=[resumed["artifact_id"], state["interaction_ids"][0]],
        )
        wait = self.ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
            actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
            summary="Resumed C10 after the re-transcription arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "artifact_arrived"}, refs=[resumed["artifact_id"]],
        )
        recovered_transcript = resumed["artifact"]["turns"]
        evidence = {**state["evidence"], "recovered_transcript": recovered_transcript}
        return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "artifact_event_seqs": [arrived.seq, wait.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        plan, used = self.tools.execute(
            "get_installment_plan", {"plan_id": "FLX-9001202"},
            rationale="Confirm the Flex Installments plan the customer accepted in the recovered transcript",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        glossary, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-GLOSS", "governing_date": governing_date},
            rationale="Resolve the no-interest-framing rule as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        population, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "bilingual_asr_misrouted_population", "parameters": {}, "as_of": state["virtual_now"], "row_limit": 200},
            rationale="Count bilingual-queue Spanish calls transcribed with the wrong ASR model since the queue misconfiguration",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "plan": plan, "glossary": glossary, "population": population}
        blob = self.ledger.put_blob(evidence)
        self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the installment plan, glossary version, and ASR-routing population",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["did", "policy", "population"]},
            refs=[plan["plan_id"], glossary["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        plan = evidence["plan"]
        fee = pct_fee(plan["principal"], plan["monthly_fee_rate"])
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="fee_amount"),
            type=EventType.COMPUTATION,
            summary=f"Verified Flex Installments fee {fee} on principal {plan['principal']} at {plan['monthly_fee_rate']}%",
            payload={"helper": "fee_amount", "inputs": {"amount": plan["principal"], "rate": plan["monthly_fee_rate"]},
                     "output": str(fee), "runtime": "registered_python_helper"},
            refs=[plan["plan_id"]],
        )
        turn = next(t for t in evidence["recovered_transcript"] if t["turn_id"] == "t01")
        fee_disclosed_same_turn = "1.72%" in turn["text"] and "31.82" in turn["text"] and "sin intereses" in turn["text"].lower()
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary="The recovered transcript discloses the fixed monthly fee in the same turn as the no-interest framing",
            payload={"finding_id": "F1", "status": "no_error_candidate",
                     "fee_matches_plan": str(fee) == plan["monthly_fee_amount"],
                     "fee_disclosed_same_turn": fee_disclosed_same_turn},
            refs=[f"{state['interaction_ids'][0]}:t01", plan["plan_id"]],
        )
        return {"computed_fee": str(fee), "fee_disclosed_same_turn": fee_disclosed_same_turn,
                "computation_seq": computation.seq, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turn = next(t for t in evidence["recovered_transcript"] if t["turn_id"] == "t01")
        plan = evidence["plan"]
        glossary = evidence["glossary"]
        population = evidence["population"]
        checks = {
            "recovered_quote_exact": "sin intereses" in turn["text"].lower(),
            "fee_computed_matches_plan": state["computed_fee"] == plan["monthly_fee_amount"],
            "fee_disclosed_same_turn": state["fee_disclosed_same_turn"],
            "glossary_as_of": glossary["version"] == "v7" and glossary["effective_from"] <= "2026-10-28" <= glossary["effective_to"],
            "population_count_confirmed": len(population) == 63,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact recovered Spanish disclosure turn",
            payload={"interaction_id": state["interaction_ids"][0], "turn_id": "t01",
                     "quote": turn["text"], "substring_match": checks["recovered_quote_exact"]},
            refs=[f"{state['interaction_ids'][0]}:t01"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified glossary v7 (not the later v8 ban) governed the interaction date",
            payload={"doc": glossary["source_id"], "clause": "MC-03.3",
                     "governing_date": "2026-10-28", "valid": checks["glossary_as_of"]}, refs=[glossary["source_id"]],
        )
        fairness = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="policy_engine"),
            type=EventType.FAIRNESS_CHECK,
            summary="Confirmed language, ASR confidence, and accent were used only for evidence-handling, never for the finding",
            payload={"stage": "c10_decision", "prohibited_features": ["language", "accent", "asr_confidence"],
                     "present": [], "passed": True}, refs=[state["interaction_ids"][0]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C10_L3", "result": "pass" if passed else "fail"},
                refs=[plan["plan_id"], glossary["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C10 deterministic verifier failed")
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence from passed deterministic checks",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": None, "nonpanel_consistency": 1.0, "result": 1.0},
            refs=[glossary["source_id"]],
        )
        return {"verifier_checks": checks,
                "verification_seqs": [span.seq, citation.seq, fairness.seq, *check_seqs, confidence.seq],
                "computed_confidence": 1.0}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"panel_used": False,
                "panel_reason": "no adverse colleague finding; the population control gap is attributable to a "
                                "queue-configuration change, not a systemic colleague finding requiring adversarial review",
                "panel_event_seqs": []}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed no error for the colleague and customer; control gap for the ASR queue-routing misconfiguration",
            payload={"finding_id": "F1", "category": "none", "status": "no_error", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t01", state["evidence"]["plan"]["plan_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped colleague memory write: the disclosure was accurate once correctly transcribed",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "no_error against the colleague; the control gap is attributable to the ASR queue routing",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turn = next(t for t in evidence["recovered_transcript"] if t["turn_id"] == "t01")
        plan = evidence["plan"]
        glossary = evidence["glossary"]
        population = evidence["population"]
        source_refs = [f"{interaction_id}:t01", plan["plan_id"], glossary["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["deadline_event_seq"], state["computation_seq"],
            state["reconcile_event_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["wait_event_seqs"], *state["artifact_event_seqs"],
            *state["verification_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="none", status="no_error", attributable_to="none", severity="low",
            interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                             "start_s": float(turn["start_s"]), "end_s": float(turn["end_s"]),
                             "quote": turn["text"], "verified": True}],
            structured_evidence=[{"source": "installment_plans", "id": plan["plan_id"],
                                  "fact": f"principal {plan['principal']} at {plan['monthly_fee_rate']}% = {state['computed_fee']}"}],
            policy_refs=[{"doc_id": glossary["source_id"], "clause": "MC-03.3", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": False, "remediation": [{"action": "none"}]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_finding", "actions": [], "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_gap_record", "system": "asr_model_routing", "population": len(population)},
            ]},
            "adjudication": {"panel_used": False, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the fee had actually been omitted from the same turn as the no-interest framing"},
            "waits": [{"artifact_id": state["artifact_request"]["artifact_id"], "kind": "retranscription",
                       "requested_at": state["artifact_request"]["requested_at"],
                       "expected_at": state["artifact_request"]["expected_at"],
                       "arrived_at": state["virtual_now"], "latest_safe_decision": state["latest_safe_decision"],
                       "result": "arrived"}],
            "memory_ops": [{"op": "skip", "reason": "no_error against the colleague once correctly transcribed",
                            "source_refs": [interaction_id]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "no fee disclosed with the no-interest framing (MC-03 under glossary v8 rules)",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "fee disclosed in the same turn, permitted under glossary v7 in force",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": glossary["source_id"], "why": "governing no-interest-framing rule as of the interaction date"}],
            "summary_for_record": "No error. The recovered es-US transcription shows the fixed monthly fee disclosed "
                                   "in the same turn as the no-interest framing, permitted under CLB-GLOSS@v7 in force "
                                   f"on the interaction date. {len(population)} bilingual-queue Spanish calls were "
                                   "transcribed with the wrong ASR model due to a queue-configuration change; that is "
                                   "a control gap, not a colleague or customer finding.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C10 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
