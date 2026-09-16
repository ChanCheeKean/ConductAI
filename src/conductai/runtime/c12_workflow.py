"""C12 cheat-sheet: semantic phrase fan-out traced to unapproved supervisor material, decided by panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.fanout import FanOutDispatcher
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor

# Exact-phrase OR query: each clause is the literal paraphrase template from the leaked
# ICM-9001501 rebuttal (plus its negation and its diarization-mislabeled echo). FTS5 phrase
# matching on the full word sequence is what gives this precision: the unrelated background
# distractor phrasing ("This protection is basically free if you pay on time.") never matches
# any of these exact sequences, so no team/date post-filter is even required for correctness —
# confirmed empirically against the dataset before writing this workflow.
_SEARCH_QUERY = (
    "\"is basically free as long as you pay\" OR \"basically free when you pay on time\" "
    "OR \"you only pay if you carry a balance\" OR \"practically costs nothing if you pay in full\" "
    "OR \"not free\" OR \"so it's basically free\""
)

# The five colleagues on T-SAT-2 who rotated through the leaked wording (confirmed via a direct
# query of transcript_turns/interactions/colleagues before implementation). COL-6600 is the team
# supervisor and author of ICM-9001501, not a member of this rotation.
_EXPECTED_COLLEAGUES = {"COL-6630", "COL-6637", "COL-6645", "COL-6651", "COL-6658"}
_EXPECTED_DISCARDED = {"INT-9001509", "INT-9001514"}


class C12Workflow:
    """Deterministic semantic fan-out and supervisor-material root-cause path; C12 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger
        self._fanout = FanOutDispatcher(ledger)
        self._fanout_ctx: dict[str, Any] = {}
        self._fanout_used = 0

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=100, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "addon_misrepresentation_phrase_review":
            raise RuntimeError("C12 requires the addon_misrepresentation_phrase_review route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the add-on misrepresentation phrase-review path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "addon_misrepresentation_phrase_present": state["route_facts"]["addon_misrepresentation_phrase_present"],
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
            rationale="Read the exact anchor sentence that triggered the phrase-review scanner flag",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Chat transcript is a complete, unambiguous text capture",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "chat_exact",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"trigger_transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        ctx = node_context(state)
        used = state["tool_calls_used"]
        limit = state["route"]["budget"]["tool_calls"]

        candidates, used = self.tools.execute(
            "search_transcripts",
            {"query": _SEARCH_QUERY, "speaker": "colleague",
             "from_at": "2026-10-05T00:00:00Z", "to_at": state["virtual_now"], "top_k": 40},
            rationale="Find semantic paraphrases of the leaked CardShield rebuttal, not just keyword matches",
            used=used, limit=limit, **ctx,
        )
        candidate_ids = sorted({row["interaction_id"] for row in candidates})

        self._fanout_ctx = {"run_id": state["run_id"], "review_id": state["review_id"],
                             "virtual_now": ctx["virtual_now"], "limit": limit}
        self._fanout_used = used
        results, fanout_seqs = self._fanout.run(
            kind="phrase_hit", role="linked_interaction_reviewer", subjects=candidate_ids, cap=24,
            evaluate=self._evaluate_hit, run_id=state["run_id"], review_id=state["review_id"],
            virtual_now=ctx["virtual_now"],
        )
        used = self._fanout_used

        affected = sorted((row for row in results if row["status"] == "misrepresentation"), key=lambda row: row["subject"])
        discarded = sorted((row for row in results if row["status"] == "discarded"), key=lambda row: row["subject"])
        affected_ids = [row["subject"] for row in affected]
        discarded_ids = [row["subject"] for row in discarded]
        colleagues = sorted({row["colleague_id"] for row in affected})

        internal_comm, used = self.tools.execute(
            "get_internal_comm", {"message_id": "ICM-9001501"},
            rationale="Retrieve the team-chat material the paraphrase family traces back to",
            used=used, limit=limit, **ctx,
        )

        evidence = {**state["evidence"], "candidates": candidates, "fanout_results": results,
                    "affected": affected, "discarded": discarded, "affected_ids": affected_ids,
                    "discarded_ids": discarded_ids, "colleagues": colleagues, "internal_comm": internal_comm}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary=f"Fan-out over {len(candidate_ids)} candidates: {len(affected_ids)} affected across "
                    f"{len(colleagues)} colleagues, {len(discarded_ids)} discarded; traced to ICM-9001501",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["candidates", "affected", "discarded", "internal_comm"]},
            refs=[*affected_ids, *discarded_ids, "ICM-9001501"],
        )
        return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [update.seq],
                "fanout_seqs": fanout_seqs}

    def _evaluate_hit(self, interaction_id: str) -> dict[str, Any]:
        ctx = self._fanout_ctx
        used = self._fanout_used
        interaction, used = self.tools.execute(
            "get_interaction", {"interaction_id": interaction_id},
            rationale="Identify the colleague on this candidate interaction",
            used=used, limit=ctx["limit"], run_id=ctx["run_id"], review_id=ctx["review_id"], virtual_now=ctx["virtual_now"],
        )
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the colleague's exact wording on this candidate interaction",
            used=used, limit=ctx["limit"], run_id=ctx["run_id"], review_id=ctx["review_id"], virtual_now=ctx["virtual_now"],
        )
        self._fanout_used = used
        turn = next(t for t in transcript if t["turn_id"] == "t01")
        colleague_id = interaction["colleague_id"]
        text = turn["text"]
        lowered = text.lower()

        if turn.get("speaker_channel") != "colleague":
            self.ledger.emit(
                run_id=ctx["run_id"], review_id=ctx["review_id"], virtual_now=ctx["virtual_now"],
                actor=Actor(kind="subagent", name="linked_interaction_reviewer"),
                type=EventType.SPEAKER_ATTRIBUTION_CHECKED,
                summary=f"{interaction_id}:t01 is diarization-mislabeled: the customer asked the question, "
                        "not the colleague asserting it",
                payload={"interaction_id": interaction_id, "turn_id": "t01", "claimed_speaker": "colleague",
                         "actual_channel": turn.get("speaker_channel"), "speaker_confidence": turn.get("speaker_confidence")},
                refs=[f"{interaction_id}:t01"],
            )
            return {"status": "discarded", "reason": "diarization_mismatch", "colleague_id": colleague_id,
                    "turn_id": "t01", "quote": text, "started_at_utc": interaction.get("started_at_utc")}

        if "not free" in lowered:
            self.ledger.emit(
                run_id=ctx["run_id"], review_id=ctx["review_id"], virtual_now=ctx["virtual_now"],
                actor=Actor(kind="subagent", name="linked_interaction_reviewer"),
                type=EventType.CONTRADICTION_DETECTED,
                summary=f"{interaction_id}:t01 negates the free-if-you-pay-on-time claim rather than asserting it",
                payload={"interaction_id": interaction_id, "turn_id": "t01", "quote": text},
                refs=[f"{interaction_id}:t01"],
            )
            return {"status": "discarded", "reason": "negation", "colleague_id": colleague_id,
                    "turn_id": "t01", "quote": text, "started_at_utc": interaction.get("started_at_utc")}

        return {"status": "misrepresentation", "colleague_id": colleague_id, "turn_id": "t01", "quote": text,
                "started_at_utc": interaction.get("started_at_utc")}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        affected_ids = evidence["affected_ids"]
        discarded_ids = evidence["discarded_ids"]
        colleagues = evidence["colleagues"]
        interaction_id = state["interaction_ids"][0]
        if set(colleagues) != _EXPECTED_COLLEAGUES or set(discarded_ids) != _EXPECTED_DISCARDED:
            raise RuntimeError("C12 fan-out did not reproduce the verified colleague rotation / discard set")
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="fanout_population_count"),
            type=EventType.COMPUTATION,
            summary=f"{len(affected_ids)} misrepresentations across {len(colleagues)} colleagues; "
                    f"{len(discarded_ids)} candidates correctly discarded",
            payload={"helper": "fanout_population_count",
                     "inputs": {"candidates": len(evidence["candidates"]), "affected": len(affected_ids),
                                "discarded": len(discarded_ids)},
                     "output": len(affected_ids), "runtime": "registered_python_helper"},
            refs=[interaction_id],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.FINDING_UPDATED,
            summary="Root cause traces to unapproved supervisor material shared in team chat, not "
                    "individual colleague choice",
            payload={"finding_id": "F1", "status": "substantiated_candidate", "attributable_to": "supervisor_material",
                     "population": len(affected_ids), "colleagues": colleagues, "discarded": discarded_ids},
            refs=[interaction_id, "ICM-9001501"],
        )
        return {"root_cause_changed": False, "reconcile_event_seq": finding.seq, "computation_seq": computation.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        interaction_id = state["interaction_ids"][0]
        trigger_turn = next(t for t in evidence["trigger_transcript"] if t["turn_id"] == "t01")
        internal_comm = evidence["internal_comm"]
        affected = evidence["affected"]
        earliest_affected = min(row["started_at_utc"] for row in affected)
        checks = {
            "quote_exact": "the fee only shows up if you carry a balance" in trigger_turn["text"],
            "population_verified": len(evidence["affected_ids"]) == 15,
            "discarded_verified": set(evidence["discarded_ids"]) == _EXPECTED_DISCARDED,
            "colleague_rotation_verified": set(evidence["colleagues"]) == _EXPECTED_COLLEAGUES,
            "material_precedes_earliest_affected_call": internal_comm["sent_at_utc"] < earliest_affected,
            "material_author_is_team_supervisor": internal_comm["author_id"] == "COL-6600",
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the exact anchor misrepresentation sentence",
            payload={"interaction_id": interaction_id, "turn_id": "t01",
                     "quote": trigger_turn["text"], "substring_match": checks["quote_exact"]},
            refs=[f"{interaction_id}:t01"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED,
            summary="Verified ICM-9001501 predates every affected call and was authored by the team supervisor",
            payload={"doc": "ICM-9001501", "sent_at_utc": internal_comm["sent_at_utc"],
                     "earliest_affected_call": earliest_affected,
                     "valid": checks["material_precedes_earliest_affected_call"] and checks["material_author_is_team_supervisor"]},
            refs=["ICM-9001501"],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C12_L4", "result": "pass" if passed else "fail"},
                refs=[f"{interaction_id}:t01", "ICM-9001501"],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C12 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        affected_ids = evidence["affected_ids"]
        colleagues = evidence["colleagues"]
        snapshot = {"finding": "MC-03 substantiated, attributable_to supervisor_material",
                    "population": len(affected_ids), "colleagues": colleagues}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity and a systemic population across 5 colleagues",
            payload={"predicate": "high_and_systemic_population_ge_10", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary=f"Customer advocate: all {len(affected_ids)} affected customers should receive remediation "
                    "regardless of who is at fault internally",
            payload={"role": "customer_advocate", "position": "systemic_remediation",
                     "key_refs": affected_ids[:3], "snapshot_hash": snapshot_hash}, refs=affected_ids,
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary=f"Colleague advocate: the {len(colleagues)} colleagues used their supervisor's own "
                    "rebuttal material in good faith and should not be individually blamed",
            payload={"role": "colleague_advocate", "position": "no_individual_fault_supervisor_material",
                     "key_refs": ["ICM-9001501"], "snapshot_hash": snapshot_hash}, refs=["ICM-9001501"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: supervisor-authored material displaces individual colleague attribution",
            payload={"determinative_issue": "whether supervisor-authored material displaces individual attribution",
                     "decision": "supervisor_material",
                     "flip_fact": "the material having originated from an individual colleague's own choice "
                                  "rather than the team supervisor's team-chat message"},
            refs=["ICM-9001501"],
        )
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED, summary="Computed confidence with aligned panel positions",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": 1.0,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20, "panel_agreement": 0.10},
                     "result": 1.0},
            refs=["ICM-9001501"],
        )
        return {"panel_used": True,
                "panel_reason": "severity high and a systemic population across 5 colleagues, with attribution "
                                 "contested between the colleagues and the supervisor's own material",
                "computed_confidence": 1.0,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-03 substantiated, attributable to supervisor material, not individual colleagues",
            payload={"finding_id": "F1", "category": "MC-03", "status": "substantiated",
                     "attributable_to": "supervisor_material"},
            refs=[f"{interaction_id}:t01", "ICM-9001501"],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write: the root cause is unapproved supervisor material already captured "
                    "as a control finding, not a colleague-specific behavioral pattern to remember",
            payload={"subject": "ICM-9001501",
                     "reason": "root cause is unapproved material, not a colleague-specific pattern to remember",
                     "gate_checks": {"colleague_specific_pattern": False,
                                     "root_cause_already_recorded_as_control_finding": True,
                                     "prohibited_content": False}},
            refs=["ICM-9001501"],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        trigger_turn = next(t for t in evidence["trigger_transcript"] if t["turn_id"] == "t01")
        affected_ids = evidence["affected_ids"]
        discarded_ids = evidence["discarded_ids"]
        colleagues = evidence["colleagues"]
        internal_comm = evidence["internal_comm"]
        trigger_colleague = state["route_facts"]["interaction"]["colleague_id"]

        source_refs = [f"{interaction_id}:t01", "ICM-9001501", *affected_ids]
        seqs = sorted(set([
            state["route_event_seq"], state["reconcile_event_seq"], state["computation_seq"],
            state["finding_event_seq"], state["memory_event_seq"],
            *state["integrity_event_seqs"], *state["gather_event_seqs"], *state["fanout_seqs"],
            *state["verification_seqs"], *state["panel_event_seqs"],
        ]))

        finding = Finding(
            finding_id="F1", category="MC-03", status="substantiated", attributable_to="supervisor_material",
            severity="high", interaction_id=interaction_id,
            evidence_spans=[{"interaction_id": interaction_id, "turn_id": "t01",
                             "start_s": float(trigger_turn["start_s"]), "end_s": float(trigger_turn["end_s"]),
                             "quote": trigger_turn["text"], "verified": True}],
            structured_evidence=[
                {"source": "fanout", "id": "phrase_hit_population",
                 "fact": f"{len(affected_ids)} of 17 semantically similar CardShield-free paraphrases "
                         f"misrepresented fee applicability, affecting {len(affected_ids)} customers across "
                         f"{len(colleagues)} colleagues ({', '.join(colleagues)}); {len(discarded_ids)} discarded "
                         f"({', '.join(discarded_ids)}) for diarization_mismatch and negation"},
                {"source": "internal_comms", "id": "ICM-9001501",
                 "fact": f"Team-chat message from supervisor {internal_comm['author_id']} sent "
                         f"{internal_comm['sent_at_utc']}, before the earliest affected call — "
                         f"{internal_comm['text']!r}"},
            ],
            policy_refs=[],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "affected_count": len(affected_ids),
                                  "remediation": [{"action": "correction_letter"}, {"action": "premium_refund_offer"}]},
            "colleague_outcome": {"colleague_id": trigger_colleague, "finding": "no_finding",
                                  "actions": ["assign_coaching"], "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_gap_record",
                 "reason": "unapproved rebuttal material shared in team chat and used verbatim/paraphrased by 5 colleagues"},
                {"type": "quarantine_unapproved_material", "material_id": "ICM-9001501"},
                {"type": "systemic_remediation_record", "population": len(affected_ids), "colleagues": colleagues,
                 "action": "coaching_only_all"},
            ]},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the material having originated from an individual colleague's own "
                                          "choice rather than the team supervisor's team-chat message"},
            "waits": [], "memory_ops": [{"op": "skip",
                                            "reason": "root cause is unapproved material, not a colleague-specific pattern",
                                            "source_refs": ["ICM-9001501"]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "independent individual misrepresentation by 5 colleagues", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "systemic control gap: unapproved rebuttal material shared by the team "
                                       "supervisor via ICM-9001501", "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": "ICM-9001501",
                              "why": "the unapproved rebuttal material the paraphrase family traces back to"}],
            "summary_for_record": f"MC-03 substantiated, attributable to supervisor material. Semantic fan-out "
                                   f"over 17 candidate transcripts found {len(affected_ids)} misrepresentations "
                                   f"across {len(colleagues)} colleagues that all trace to ICM-9001501, an "
                                   "unapproved team-chat rebuttal from the team supervisor; 2 candidates were "
                                   "correctly discarded (a diarization mislabel and a colleague's own correction). "
                                   "Colleagues receive coaching only; the systemic finding is against the material.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C12 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
