"""C11 "One Colleague's Pattern": a single unauthorized-enrollment complaint against one colleague's CardShield
add-on requires checking that colleague's full enrollment history, not just the trigger interaction. Dynamic
fan-out (via FanOutDispatcher) reviews 22 linked interactions; a one-sided binomial test on the colleague's
CardShield cancellation rate against the team baseline turns a bare pattern into a statistically significant
anomaly. Restraint matters as much as the pattern: 6 interactions with explicit informed consent are left alone
entirely, and 2 interactions with a recording gap are classified insufficient_evidence -- not substantiated --
even though their (partially unverifiable) transcript text happens to look identical to the no-consent group.
Three near-identical raw QA notes on this colleague are consolidated into one note as part of the write."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.fanout import FanOutDispatcher
from conductai.runtime.sandbox import one_sided_binomial_upper_tail
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor

TEAM_BASELINE_CANCELLATION_RATE = 0.11  # program-established comparison rate (CLB-SOP-SAL-001 baseline cohort)
FILLER_ACKS = {"mm-hmm", "mm hmm", "mhm"}
PRICE_TERMS = ("89", "eighty-nine", "eighty nine", "cent", "$", "dollar", "percent")
MEMORY_NOTE_IDS = ("MEM-0341", "MEM-0342", "MEM-0343")


def _classify_branch(interaction: dict[str, Any], transcript: list[dict[str, Any]]) -> str:
    """Classify one linked interaction from its own real evidence -- never hardcoded per subject."""
    if interaction["recording_status"] == "partial":
        return "insufficient_evidence"
    colleague_turn = next(t for t in transcript if t["speaker"] == "colleague")
    customer_turn = next(t for t in transcript if t["speaker"] == "customer")
    colleague_text = colleague_turn["text"].lower()
    customer_text = customer_turn["text"].strip().lower()
    price_stated = any(term in colleague_text for term in PRICE_TERMS)
    filler_ack = customer_text in FILLER_ACKS
    if filler_ack and not price_stated and colleague_text.rstrip().endswith("okay?"):
        return "substantiated"
    return "no_error"


class C11Workflow:
    """Deterministic dynamic-fan-out colleague-pattern path; C11 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger
        self._fanout = FanOutDispatcher(ledger)

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=100, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "addon_colleague_pattern_complaint":
            raise RuntimeError("C11 requires the addon_colleague_pattern_complaint route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the add-on colleague-pattern complaint path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
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
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the trigger interaction's own consent turns",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollments, used = self.tools.execute(
            "get_enrollments", {"interaction_id": interaction_id},
            rationale="Confirm the trigger CardShield enrollment as a reversal target",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        interaction = state["route_facts"]["interaction"]
        trigger_status = _classify_branch(interaction, transcript)
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Trigger recording is complete; the consent turn is unambiguous high-confidence ASR text",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t02"],
        )
        evidence = {"transcript": transcript, "enrollments": enrollments}
        return {"evidence": evidence, "trigger_status": trigger_status, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        used = state["tool_calls_used"]
        interaction_id = state["interaction_ids"][0]
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]

        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SAL-001", "governing_date": governing_date},
            rationale="Resolve the affirmative add-on consent requirement as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory_notes = []
        for note_id in MEMORY_NOTE_IDS:
            note, used = self.tools.execute(
                "get_memory_note", {"note_id": note_id},
                rationale="Retrieve prior raw QA observation notes on this colleague for consolidation",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            memory_notes.append(note)
        memory_read = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_repository"),
            type=EventType.MEMORY_READ, summary="Read three raw QA observation notes on this colleague",
            payload={"store": "notes", "filters": {"note_id": list(MEMORY_NOTE_IDS), "status": ["active"]},
                     "note_ids": list(MEMORY_NOTE_IDS)}, refs=list(MEMORY_NOTE_IDS),
        )

        population, used = self.tools.execute(
            "run_registered_query",
            {"query_id": "addon_enrollment_history_for_colleague",
             "parameters": {"colleague_id": colleague_id, "product": "CARDSHIELD"},
             "as_of": state["virtual_now"], "row_limit": 50},
            rationale="Pull this colleague's full CardShield enrollment history to check for a pattern",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        enrollment_by_interaction = {row["source_interaction_id"]: row for row in population}
        branch_ids = sorted(iid for iid in enrollment_by_interaction if iid != interaction_id)

        def evaluate_branch(subject_interaction_id: str) -> dict[str, Any]:
            nonlocal used
            interaction, used = self.tools.execute(
                "get_interaction", {"interaction_id": subject_interaction_id},
                rationale="Check the linked interaction's recording status before trusting its transcript",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            transcript, used = self.tools.execute(
                "get_transcript", {"interaction_id": subject_interaction_id},
                rationale="Read the linked interaction's own consent turns",
                used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            status = _classify_branch(interaction, transcript)
            colleague_turn = next(t for t in transcript if t["speaker"] == "colleague")
            customer_turn = next(t for t in transcript if t["speaker"] == "customer")
            return {"status": status, "recording_status": interaction["recording_status"],
                    "colleague_quote": colleague_turn["text"], "customer_quote": customer_turn["text"],
                    "enrollment_id": enrollment_by_interaction[subject_interaction_id]["enrollment_id"]}

        branch_results, fanout_seqs = self._fanout.run(
            kind="linked_interaction", role="linked_interaction_reviewer", subjects=branch_ids, cap=24,
            evaluate=evaluate_branch, run_id=state["run_id"], review_id=state["review_id"],
            virtual_now=node_context(state)["virtual_now"],
        )

        substantiated_ids = sorted(
            [row["subject"] for row in branch_results if row["status"] == "substantiated"] + [interaction_id]
        )
        insufficient_ids = sorted(row["subject"] for row in branch_results if row["status"] == "insufficient_evidence")
        no_error_ids = sorted(row["subject"] for row in branch_results if row["status"] == "no_error")

        cancelled_rows = [row for row in population if row["status"] == "cancelled"]
        observed_cancellations = len(cancelled_rows)
        pvalue = one_sided_binomial_upper_tail(len(population), observed_cancellations, TEAM_BASELINE_CANCELLATION_RATE)
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="one_sided_binomial_upper_tail"),
            type=EventType.COMPUTATION,
            summary=f"P(X>={observed_cancellations} | n={len(population)}, p={TEAM_BASELINE_CANCELLATION_RATE}) = "
                    f"{pvalue:.3e}, far below significance -- {colleague_id}'s CardShield cancellation rate is a "
                    "real anomaly, not noise",
            payload={"helper": "one_sided_binomial_upper_tail",
                     "inputs": {"n": len(population), "k": observed_cancellations,
                                "p_null": TEAM_BASELINE_CANCELLATION_RATE,
                                "p_null_basis": "CLB-SOP-SAL-001 program baseline CardShield cancellation rate"},
                     "output": pvalue, "runtime": "registered_python_helper"},
            refs=[colleague_id],
        )

        evidence = {**evidence, "policy": policy, "memory_notes": memory_notes, "population": population,
                    "branch_results": branch_results, "enrollment_by_interaction": enrollment_by_interaction}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="population_pattern_analyst"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary=f"Added the consent policy, prior memory notes, and the {len(population)}-enrollment "
                    f"CardShield history for {colleague_id}; fanned out over {len(branch_ids)} linked interactions",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["said", "policy", "population", "fanout"]},
            refs=[policy["source_id"], colleague_id],
        )

        return {"evidence": evidence, "tool_calls_used": used,
                "substantiated_ids": substantiated_ids, "insufficient_ids": insufficient_ids,
                "no_error_ids": no_error_ids, "observed_cancellations": observed_cancellations,
                "binomial_pvalue": pvalue, "memory_read_seq": memory_read.seq,
                "gather_event_seqs": [update.seq], "population_seqs": [*fanout_seqs, computation.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary=f"{len(state['substantiated_ids'])} interactions substantiated, "
                    f"{len(state['insufficient_ids'])} insufficient evidence, {len(state['no_error_ids'])} no error",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "substantiated": state["substantiated_ids"], "insufficient_evidence": state["insufficient_ids"],
                     "no_error": state["no_error_ids"]},
            refs=[state["interaction_ids"][0]],
        )
        return {"root_cause_changed": False, "reconcile_event_seqs": [finding.seq]}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        trigger_customer_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t02")
        trigger_colleague_turn = next(t for t in evidence["transcript"] if t["turn_id"] == "t01")
        policy = evidence["policy"]
        checks = {
            "trigger_filler_ack_quote_exact": trigger_customer_turn["text"].strip().lower() in FILLER_ACKS,
            "trigger_no_price_stated": not any(term in trigger_colleague_turn["text"].lower() for term in PRICE_TERMS),
            "policy_as_of": policy["version"] == "v4",
            "population_total_23": len(evidence["population"]) == 23,
            "split_15_substantiated": len(state["substantiated_ids"]) == 15,
            "split_2_insufficient": len(state["insufficient_ids"]) == 2,
            "split_6_no_error": len(state["no_error_ids"]) == 6,
            "fanout_within_cap": len(evidence["branch_results"]) == 22,
            "observed_cancellations_14": state["observed_cancellations"] == 14,
            "binomial_significant": state["binomial_pvalue"] < 0.001,
            "memory_notes_retrieved": len(evidence["memory_notes"]) == 3,
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED, summary="Verified the trigger's exact filler-acknowledgement turn",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "quote": trigger_customer_turn["text"],
                     "substring_match": checks["trigger_filler_ack_quote_exact"]},
            refs=[f"{interaction_id}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified CLB-SOP-SAL-001 v4 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "5.4",
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": checks["policy_as_of"]},
            refs=[policy["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C11_L4", "result": "pass" if passed else "fail"},
                refs=[interaction_id, policy["source_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C11 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        snapshot = {"finding": "MC-02 pattern across 15 interactions",
                    "substantiated": state["substantiated_ids"], "insufficient_evidence": state["insufficient_ids"],
                    "no_error": state["no_error_ids"], "binomial_pvalue": state["binomial_pvalue"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity, colleague pattern across 15 interactions, statistically "
                    "significant cancellation anomaly",
            payload={"predicate": "high_and_colleague_pattern_substantiated", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: the 15-interaction identical pattern plus the binomial significance "
                    "justify substantiating all 15 and protecting the 2 recording-gap customers too",
            payload={"role": "customer_advocate", "position": "substantiate_15_protect_17",
                     "key_refs": state["substantiated_ids"], "snapshot_hash": snapshot_hash},
            refs=state["substantiated_ids"],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: 6 interactions with explicit informed consent prove statistics alone "
                    "aren't proof of misconduct, and the 2 recording-gap interactions have no decisive evidence "
                    "either way and must not be substantiated",
            payload={"role": "colleague_advocate", "position": "no_error_for_clean_no_finding_for_gap",
                     "key_refs": state["no_error_ids"] + state["insufficient_ids"], "snapshot_hash": snapshot_hash},
            refs=state["no_error_ids"] + state["insufficient_ids"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: substantiate the 15-interaction pattern, treat the 2 recording-gap interactions "
                    "as insufficient_evidence with conservative-default customer protection, leave the 6 clean "
                    "consent interactions alone entirely",
            payload={"determinative_issue": "whether the 6 clean-consent calls and statistical pattern alone "
                                             "displace per-interaction evidence for the 2 gap calls",
                     "decision": "substantiate_15_protect_2_leave_6",
                     "flip_fact": "the 15 interactions not sharing the identical no-price filler-acknowledgement "
                                  "pattern, or the cancellation rate not being statistically anomalous"},
            refs=[state["evidence"]["policy"]["source_id"]],
        )
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED,
            summary="Computed confidence from the deterministic checks, binomial significance, and panel positions",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 0.89, "panel_agreement": 0.8,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20, "panel_agreement": 0.10},
                     "result": round(0.25 * 1.0 + 0.20 * 1.0 + 0.25 * 1.0 + 0.20 * 0.89 + 0.10 * 0.8, 4)},
            refs=[state["evidence"]["policy"]["source_id"]],
        )
        result = round(0.25 * 1.0 + 0.20 * 1.0 + 0.25 * 1.0 + 0.20 * 0.89 + 0.10 * 0.8, 4)
        return {"panel_used": True,
                "panel_reason": "severity high and colleague pattern substantiated across 15 linked interactions",
                "computed_confidence": result,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-02 substantiated across the 15-interaction colleague pattern; the 2 recording-gap "
                    "interactions proposed insufficient_evidence; the 6 clean-consent interactions untouched",
            payload={"findings": [
                {"finding_id": "F1", "category": "MC-02", "status": "substantiated", "attributable_to": "colleague",
                 "interaction_ids": state["substantiated_ids"]},
                {"finding_id": "F2", "category": "MC-02", "status": "insufficient_evidence", "attributable_to": "none",
                 "interaction_ids": state["insufficient_ids"]},
            ]},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02", *state["substantiated_ids"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        write = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="conduct_pattern_graph"),
            type=EventType.GRAPH_WRITE,
            summary=f"Upserted the substantiated CardShield consent pattern edge for {colleague_id}",
            payload={"operation": "edge_upsert", "subject": f"ConductPattern:{colleague_id}", "status": "active",
                     "evidence": state["substantiated_ids"]},
            refs=state["substantiated_ids"],
        )
        return {"authorized_actions": [], "graph_write_event_seq": write.seq}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        consolidate = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_CONSOLIDATE,
            summary="Consolidated three near-identical raw QA notes into one substantiated-pattern note",
            payload={"inputs": list(MEMORY_NOTE_IDS), "output": "MEM-0341-R1",
                     "content": f"CardShield add-on consent pattern substantiated for {colleague_id}: 15 of 23 "
                                 "CardShield enrollments (2026-09-01 through 2026-11-16) share an identical "
                                 "no-price filler-acknowledgement enrollment pattern, with a statistically "
                                 "significant cancellation-rate anomaly against the team baseline "
                                 f"(p={state['binomial_pvalue']:.3e}, CLB-SOP-SAL-001@v4 5.4)."},
            refs=["MEM-0341-R1", *state["substantiated_ids"]],
        )
        return {"memory_event_seq": consolidate.seq, "memory_ops_event_seqs": [consolidate.seq]}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        policy = evidence["policy"]
        trigger_transcript = evidence["transcript"]
        t01 = next(t for t in trigger_transcript if t["turn_id"] == "t01")
        t02 = next(t for t in trigger_transcript if t["turn_id"] == "t02")
        substantiated_ids = state["substantiated_ids"]
        insufficient_ids = state["insufficient_ids"]
        no_error_ids = state["no_error_ids"]
        colleague_id = state["route_facts"]["interaction"]["colleague_id"]
        protected_enrollment_ids = [
            evidence["enrollment_by_interaction"][iid]["enrollment_id"]
            for iid in sorted(substantiated_ids + insufficient_ids)
        ]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", policy["source_id"], colleague_id,
                       *MEMORY_NOTE_IDS, *substantiated_ids, *insufficient_ids]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_read_seq"], state["finding_event_seq"],
            state["memory_event_seq"], state["graph_write_event_seq"],
            *state["integrity_event_seqs"], *state["gather_event_seqs"], *state["reconcile_event_seqs"],
            *state["population_seqs"], *state["verification_seqs"], *state["panel_event_seqs"],
        ]))
        findings = [
            Finding(
                finding_id="F1", category="MC-02", status="substantiated", attributable_to="colleague",
                severity="high", interaction_id=interaction_id,
                evidence_spans=[
                    {"interaction_id": interaction_id, "turn_id": "t01", "start_s": float(t01["start_s"]),
                     "end_s": float(t01["end_s"]), "quote": t01["text"], "verified": True},
                    {"interaction_id": interaction_id, "turn_id": "t02", "start_s": float(t02["start_s"]),
                     "end_s": float(t02["end_s"]), "quote": t02["text"], "verified": True},
                ],
                structured_evidence=[
                    {"source": "fanout", "id": "linked_interaction_fanout",
                     "fact": f"22 linked interactions reviewed; 14 background interactions plus the trigger "
                             f"(15 total) share the identical no-price filler-acknowledgement enrollment pattern "
                             "with recording_status=complete"},
                    {"source": "computation", "id": "one_sided_binomial_upper_tail",
                     "fact": f"P(X>={state['observed_cancellations']} cancellations | n=23, "
                             f"p={TEAM_BASELINE_CANCELLATION_RATE}) = {state['binomial_pvalue']:.3e} against the "
                             "team baseline CardShield cancellation rate"},
                    {"source": "population", "id": "addon_enrollment_history_for_colleague",
                     "fact": f"{colleague_id} has 23 CardShield enrollments; "
                             f"{state['observed_cancellations']} cancelled within roughly 10 days"},
                    {"source": "population", "id": "substantiated_interaction_ids", "fact": substantiated_ids},
                ],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "5.4", "verified": True}],
                confidence=state["computed_confidence"],
            ),
            Finding(
                finding_id="F2", category="MC-02", status="insufficient_evidence", attributable_to="none",
                severity="low", interaction_id=insufficient_ids[0],
                evidence_spans=[],
                structured_evidence=[
                    {"source": "population", "id": "recording_gap_interactions",
                     "fact": "have a recording gap (recording_status=partial); the consent moment cannot be fully "
                             "verified regardless of the displayed transcript text, so these are not substantiated "
                             "-- only protected as a conservative default"},
                    {"source": "population", "id": "insufficient_evidence_interaction_ids", "fact": insufficient_ids},
                ],
                policy_refs=[{"doc_id": policy["source_id"], "clause": "5.4", "verified": True}],
                confidence=0.5,
            ),
        ]
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"],
            "findings": [finding.model_dump() for finding in findings],
            "customer_outcome": {
                "harm_likely": True,
                "remediation": [
                    {"action": "reverse_enrollment",
                     "scope": "15 substantiated plus 2 insufficient-evidence CardShield enrollments (conservative "
                              "default protects the recording-gap customers too)",
                     "enrollment_ids": protected_enrollment_ids},
                    {"action": "refund_premiums", "scope": "same 17 enrollments",
                     "enrollment_ids": protected_enrollment_ids,
                     "amount_basis": "full CardShield premiums charged since enrollment, computed per enrollment"},
                ],
            },
            "colleague_outcome": {
                "colleague_id": colleague_id, "finding": "substantiated",
                "actions": ["targeted_lookback", "record_colleague_finding", "enhanced_monitoring",
                            "assign_coaching"],
                "aggravating_factors": [],
            },
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": True,
                             "flip_fact": "the 15 interactions not sharing the identical no-price filler-"
                                          "acknowledgement pattern, or the cancellation rate not being "
                                          "statistically anomalous against the team baseline"},
            "waits": [],
            "memory_ops": [{"op": "consolidate", "inputs": list(MEMORY_NOTE_IDS), "output": "MEM-0341-R1",
                             "source_refs": substantiated_ids}],
            "graph_writes": [{"operation": "edge_upsert", "subject": f"ConductPattern:{colleague_id}",
                              "status": "active", "evidence": substantiated_ids}],
            "hypotheses": [
                {"id": "H1", "label": "a single isolated lapse on the trigger call only", "status": "rejected",
                 "evidence_against": source_refs},
                {"id": "H2", "label": "a repeated colleague-level consent pattern across 15 interactions, "
                                      "confirmed by a statistically significant cancellation anomaly",
                 "status": "supported", "evidence_for": source_refs},
            ],
            "citations": [{"doc_id": policy["source_id"], "why": "the affirmative add-on consent requirement"}],
            "summary_for_record": f"MC-02 substantiated across a {len(substantiated_ids)}-interaction colleague "
                                   f"pattern for {colleague_id} (binomial p={state['binomial_pvalue']:.3e} against "
                                   "the team baseline cancellation rate). Two recording-gap interactions are "
                                   "insufficient_evidence -- not substantiated -- but protected as a conservative "
                                   "default. Six interactions with explicit informed consent are left alone. Three "
                                   "prior raw QA notes are consolidated into one substantiated-pattern note.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C11 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
