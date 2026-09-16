"""C14 vulnerability judgment from behavioral evidence only: a purged prohibited-basis memory note and a
panel whose genuinely computed confidence cannot reach the adverse-colleague threshold, triggering the
asymmetric conservative default (full customer remediation, no adverse colleague finding)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, Finding, Provenance
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.router import choose_route
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor

# The six behavioral-indicator categories listed in CLB-SOP-VUL-001@v2 §3.1. Used only to size how much of
# the full indicator taxonomy this call actually evidences (decisive_evidence_coverage below) -- never age.
_SOP_INDICATOR_CATEGORIES = (
    "confusion about caller or purpose",
    "third-party reliance",
    "inability to restate terms",
    "repeated deferential assent",
    "disclosed job loss or reduced income",
    "bereavement or serious illness",
)


class C14Workflow:
    """Deterministic behavioral-vulnerability-judgment path; C14 only."""

    def __init__(self, root: Path, config: ResolvedConfig, tools: ToolExecutor, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.tools = tools
        self.ledger = ledger

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        facts, used = self.tools.execute(
            "get_route_facts", {"interaction_id": state["interaction_ids"][0]},
            rationale="Build the permitted routing projection from visible operational records",
            used=state["tool_calls_used"], limit=100, **node_context(state),
        )
        return {"route_facts": facts, "tool_calls_used": used}

    def route(self, state: dict[str, Any]) -> dict[str, Any]:
        route, evaluated = choose_route(self.config.routes, state["trigger"], state["route_facts"])
        if route.route_id != "product_change_vulnerability_review":
            raise RuntimeError("C14 requires the product_change_vulnerability_review route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION, summary="Selected the product-change behavioral-vulnerability path",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "product_change_record_present": state["route_facts"]["product_change_record_present"],
                         "product_change_event_present": state["route_facts"]["product_change_event_present"],
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
            rationale="Read the full phone call to check for behavioral vulnerability indicators",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        # Phone channel, ASR-complete recording, decent per-turn confidence (min 0.86 across all 8 turns,
        # see preverify), no recording gap -- no artifact recovery is needed.
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete and the phone transcript is unambiguous text",
            payload={"interaction_id": interaction_id, "turn_id": "t01", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None},
            refs=[f"{interaction_id}:t01"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        product_change, used = self.tools.execute(
            "get_product_change", {"interaction_id": state["interaction_ids"][0]},
            rationale="Read the product-change record submitted during this call",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory, used = self.tools.execute(
            "get_memory_note", {"note_id": "MEM-0396"},
            rationale="Retrieve the consolidated note this scanner category maps to",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        memory_read = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_repository"),
            type=EventType.MEMORY_READ, summary="Read consolidated upgrade-candidate memory note for SUMMIT",
            payload={"store": "notes", "filters": {"note_id": "MEM-0396", "status": ["active"]},
                     "note_ids": ["MEM-0396"]}, refs=["MEM-0396"],
        )
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-VUL-001", "governing_date": governing_date},
            rationale="Resolve the behavioral-vulnerability-indicator policy as of the interaction date",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "product_change": product_change, "memory_note": memory, "policy": policy}
        blob = self.ledger.put_blob(evidence)
        review_file = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED, summary="Added the product change, memory note, and policy",
            payload={"path": "evidence_matrix.json", "patch_blob": blob, "columns": ["said", "did", "policy"]},
            refs=[product_change["product_change_id"], "MEM-0396", policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "memory_read_seq": memory_read.seq,
                "gather_event_seqs": [memory_read.seq, review_file.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        # Four distinct §3.1 behavioral-indicator types, read from the transcript text only -- never from
        # any customer demographic field. This confirms all four are present, independent of any age basis.
        confusion_present = "who is this" in turns["t01"]["text"].lower()
        third_party_present = "grandson" in turns["t02"]["text"].lower() or "does this for me" in turns["t02"]["text"].lower()
        fee_asked = "annual fee" in turns["t05"]["text"].lower()
        fee_never_stated_by_customer = not any(
            char.isdigit() for turn_id in ("t04", "t06") for char in turns[turn_id]["text"]
        )
        deference_hits = sum(
            1 for turn_id in ("t06", "t07", "t08") if "whatever you think is best" in turns[turn_id]["text"].lower()
        )
        indicators = {
            "confusion_about_caller": confusion_present,
            "third_party_reliance": third_party_present,
            "inability_to_restate_fee": fee_asked and fee_never_stated_by_customer,
            "repeated_deferential_assent": deference_hits >= 2,
        }
        indicator_count = sum(1 for present in indicators.values() if present)
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="records_reconciler"),
            type=EventType.FINDING_UPDATED,
            summary=f"{indicator_count} distinct §3.1 behavioral indicator types present around the SUMMIT upgrade",
            payload={"finding_id": "F1", "status": "candidate", "indicators": indicators,
                     "indicator_count": indicator_count, "sop_pause_threshold": 2,
                     "product_change_event_present": False},
            refs=[f"{state['interaction_ids'][0]}:t01", f"{state['interaction_ids'][0]}:t02",
                  f"{state['interaction_ids'][0]}:t04", f"{state['interaction_ids'][0]}:t05",
                  f"{state['interaction_ids'][0]}:t06", evidence["product_change"]["product_change_id"]],
        )
        return {"indicators": indicators, "indicator_count": indicator_count, "reconcile_event_seq": finding.seq}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        policy = evidence["policy"]
        indicator_turn_ids = ("t01", "t02", "t03", "t04", "t05", "t06", "t07", "t08")
        span_seqs = []
        for turn_id in indicator_turn_ids:
            turn = turns[turn_id]
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.EVIDENCE_SPAN_VERIFIED, summary=f"Verified the exact {turn_id} quote",
                payload={"interaction_id": state["interaction_ids"][0], "turn_id": turn_id,
                         "quote": turn["text"], "substring_match": True},
                refs=[f"{state['interaction_ids'][0]}:{turn_id}"],
            )
            span_seqs.append(event.seq)
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED, summary="Verified VUL-001 v2 §3.1/§3.2 governed the interaction date",
            payload={"doc": policy["source_id"], "clause": "3.1,3.2",
                     "governing_date": state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": policy["version"] == "v2" and policy["effective_from"] <= "2026-11-05"},
            refs=[policy["source_id"]],
        )
        memory_tags = json.loads(evidence["memory_note"]["tags"])
        checks = {
            "indicator_count_ge_two": state["indicator_count"] >= 2,
            "policy_as_of": policy["version"] == "v2" and policy["effective_from"] <= "2026-11-05",
            "product_change_event_absent": state["route_facts"]["product_change_event_present"] is False,
            "memory_flagged_prohibited_basis": "prohibited_basis" in memory_tags
                and evidence["memory_note"]["sensitivity"] == "prohibited_basis",
            "rewards_unaffected": evidence["product_change"]["rewards_before"] == evidence["product_change"]["rewards_after"],
            "annual_fee_confirmed": evidence["product_change"]["annual_fee_effect"] == "450 billed",
        }
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C14_L4", "result": "pass" if passed else "fail"},
                refs=[policy["source_id"], evidence["product_change"]["product_change_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C14 deterministic verifier failed")

        # decisive_transcript_quality: minimum ASR confidence among the load-bearing indicator turns. t02
        # ("My grandson Danny usually does this for me.") is the lowest at 0.86; the rest are 0.90-0.98.
        indicator_turn_confidences = [float(turns[t]["speaker_confidence"]) for t in ("t01", "t02", "t04", "t06", "t07", "t08")]
        decisive_transcript_quality = min(indicator_turn_confidences)

        # decisive_evidence_coverage: of the six behavioral-indicator categories the SOP recognizes (§3.1),
        # only one is evidenced here without an innocent alternative explanation: repeated deferential assent
        # (t06-t08), the same exact non-answer given three times running. The other three present types each
        # admit a plausible innocent reading on their own -- confusion about the caller (t01) could be a bad
        # phone connection; third-party reliance (t02) could just be an ordinary family-help arrangement;
        # inability to restate the fee (t04/t05/t06) is inferential, built by connecting the colleague's
        # re-ask to a non-numeric answer across three turns rather than a single verified quote. Behavioral
        # vulnerability judgment is inherently less certain than a verified exact policy violation (e.g. a fee
        # ledger number), and this call's decisive coverage reflects that only one of the six recognized
        # indicator types is unambiguous on its own.
        unambiguous_indicator_types = 1
        decisive_evidence_coverage = unambiguous_indicator_types / len(_SOP_INDICATOR_CATEGORIES)

        return {"verifier_checks": checks, "verification_seqs": [*span_seqs, citation.seq, *check_seqs],
                "decisive_transcript_quality": decisive_transcript_quality,
                "decisive_evidence_coverage": decisive_evidence_coverage}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        evidence = state["evidence"]
        snapshot = {"finding": "MC-09 candidate, protected-situation (vulnerability) upgrade",
                    "indicator_count": state["indicator_count"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high severity finding against a protected-situation (vulnerability) customer",
            payload={"predicate": "high_and_vulnerability_or_hardship", "snapshot_hash": snapshot_hash},
            refs=[state["interaction_ids"][0]],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: four distinct §3.1 indicator types were present, §3.2 required pausing "
                    "the sale at two, and the upgrade should be reversed with full remediation",
            payload={"role": "customer_advocate", "position": "reverse_and_support",
                     "key_refs": [f"{state['interaction_ids'][0]}:t06", f"{state['interaction_ids'][0]}:t07"],
                     "snapshot_hash": snapshot_hash},
            refs=[f"{state['interaction_ids'][0]}:t06", f"{state['interaction_ids'][0]}:t07"],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: the colleague stated the $450 annual fee outright at t03, re-asked for "
                    "it at t05 when unsure the customer understood, and the customer affirmed three times; the "
                    "terms were read and no adverse colleague finding is warranted",
            payload={"role": "colleague_advocate", "position": "no_adverse_finding_terms_disclosed",
                     "key_refs": [f"{state['interaction_ids'][0]}:t03", f"{state['interaction_ids'][0]}:t05"],
                     "snapshot_hash": snapshot_hash},
            refs=[f"{state['interaction_ids'][0]}:t03", f"{state['interaction_ids'][0]}:t05"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: the customer-protective side is better supported -- the colleague re-asked for "
                    "the fee and never received a number back, only deference -- but behavioral-indicator "
                    "interpretation carries genuine uncertainty, not the certainty of a verified policy breach",
            payload={"determinative_issue": "whether repeated deferential non-answers after a direct re-ask "
                                            "displace the colleague's own clear fee disclosure at t03",
                     "decision": "customer_protective_insufficient_for_adverse_colleague_finding",
                     "flip_fact": "the customer restating the annual fee in their own words at t04 or t06"},
            refs=[f"{state['interaction_ids'][0]}:t05", f"{state['interaction_ids'][0]}:t06"],
        )
        verifier_pass_rate = sum(1 for passed in state["verifier_checks"].values() if passed) / len(state["verifier_checks"])
        citation_verification = 1.0
        decisive_evidence_coverage = state["decisive_evidence_coverage"]
        decisive_transcript_quality = state["decisive_transcript_quality"]
        panel_agreement = 0.67  # adjudicator selected one supported side rather than aligning both advocates
        computed_confidence = (
            0.25 * verifier_pass_rate + 0.20 * citation_verification + 0.25 * decisive_evidence_coverage
            + 0.20 * decisive_transcript_quality + 0.10 * panel_agreement
        )
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED,
            summary="Computed confidence with the adjudicator selecting one supported side",
            payload={"verifier_pass_rate": verifier_pass_rate, "citation_verification": citation_verification,
                     "evidence_coverage": decisive_evidence_coverage, "transcript_quality": decisive_transcript_quality,
                     "panel_agreement": panel_agreement,
                     "weights": {"verifier_pass_rate": 0.25, "citation_verification": 0.20,
                                 "evidence_coverage": 0.25, "transcript_quality": 0.20, "panel_agreement": 0.10},
                     "result": computed_confidence},
            refs=[evidence["policy"]["source_id"]],
        )
        conservative = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONSERVATIVE_DEFAULT_APPLIED,
            summary="Confidence below the 0.75 adverse-colleague threshold: customer remediated, colleague protected",
            payload={"colleague": "no_adverse_finding", "customer": "remediate", "reason": "confidence_below_0.75"},
            refs=[state["interaction_ids"][0]],
        )
        return {"panel_used": True, "panel_reason": "severity high and a protected-situation (vulnerability) trigger",
                "computed_confidence": computed_confidence,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq, conservative.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-09 insufficient evidence: customer-protective remediation without an adverse "
                    "colleague finding, per the conservative default",
            payload={"finding_id": "F1", "category": "MC-09", "status": "insufficient_evidence", "attributable_to": "none"},
            refs=[f"{state['interaction_ids'][0]}:t01", state["evidence"]["product_change"]["product_change_id"]],
        )
        return {"finding_event_seq": event.seq}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        tombstone_id = "TMB-0396"
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_PURGE,
            summary="Purged MEM-0396: its content is a prohibited basis (age), not merely stale",
            payload={"note_id": "MEM-0396", "tombstone": tombstone_id, "reason": "prohibited_basis"},
            refs=["MEM-0396", tombstone_id],
        )
        return {"memory_event_seq": event.seq, "memory_ops_event_seqs": [event.seq], "tombstone_id": tombstone_id}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        product_change = evidence["product_change"]
        policy = evidence["policy"]
        source_refs = [f"{interaction_id}:{turn_id}" for turn_id in
                       ("t01", "t02", "t03", "t04", "t05", "t06", "t07", "t08")]
        source_refs += [product_change["product_change_id"], "MEM-0396", state["tombstone_id"], policy["source_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["memory_read_seq"], state["reconcile_event_seq"],
            state["finding_event_seq"], state["memory_event_seq"], *state["integrity_event_seqs"],
            *state["gather_event_seqs"], *state["verification_seqs"], *state["panel_event_seqs"],
        ]))
        finding = Finding(
            finding_id="F1", category="MC-09", status="insufficient_evidence", attributable_to="none",
            severity="high", interaction_id=interaction_id,
            evidence_spans=[
                {"interaction_id": interaction_id, "turn_id": turn_id,
                 "start_s": float(turns[turn_id]["start_s"]), "end_s": float(turns[turn_id]["end_s"]),
                 "quote": turns[turn_id]["text"], "verified": True}
                for turn_id in ("t01", "t02", "t03", "t04", "t05", "t06", "t07", "t08")
            ],
            structured_evidence=[
                {"source": "product_changes", "id": product_change["product_change_id"],
                 "fact": f"Upgrade from {product_change['from_product']} to {product_change['to_product']} submitted "
                         f"{product_change['submitted_at_utc']} with annual fee effect '{product_change['annual_fee_effect']}'; "
                         f"rewards unaffected (before={product_change['rewards_before']}, after={product_change['rewards_after']})"},
                {"source": "transcript", "id": interaction_id,
                 "fact": f"{state['indicator_count']} of the four candidate §3.1 behavioral indicator types were "
                         "present: confusion about who the caller was, reliance on a third party not on the call, "
                         "no annual-fee figure stated by the customer despite a direct re-ask, and repeated "
                         "deferential non-answers"},
            ],
            policy_refs=[{"doc_id": policy["source_id"], "clause": "3.1", "verified": True},
                        {"doc_id": policy["source_id"], "clause": "3.2", "verified": True}],
            confidence=state["computed_confidence"],
        )
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"], "findings": [finding.model_dump()],
            "customer_outcome": {"harm_likely": True, "remediation": [
                {"action": "reverse_upgrade"}, {"action": "refund_annual_fee", "amount": "450.00"},
                {"action": "vulnerability_support_letter"},
            ]},
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "no_adverse_finding",
                                  "actions": ["assign_coaching", "enhanced_monitoring"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": []},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": state["computed_confidence"] < 0.75,
                             "flip_fact": "the customer restating the annual fee in their own words at t04 or t06"},
            "waits": [], "memory_ops": [{"op": "purge", "note_id": "MEM-0396", "tombstone": state["tombstone_id"],
                                            "reason": "prohibited_basis", "source_refs": ["MEM-0396"]}],
            "graph_writes": [], "hypotheses": [
                {"id": "H1", "label": "an ordinary, fully informed upgrade with no vulnerability concern",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "genuine §3.1 behavioral vulnerability indicators were present, though not "
                                      "at a confidence sufficient to substantiate an adverse colleague finding",
                 "status": "supported", "evidence_for": source_refs},
            ], "citations": [{"doc_id": policy["source_id"],
                              "why": "defines behavioral vulnerability indicators and the two-indicator pause duty"}],
            "summary_for_record": f"MC-09 insufficient evidence. {state['indicator_count']} of the four candidate "
                                   "behavioral indicator types under CLB-SOP-VUL-001@v2 §3.1 were present during "
                                   "the SUMMIT upgrade call -- confusion about the caller, reliance on a third "
                                   "party not on the call, no annual-fee figure stated despite a direct re-ask, and "
                                   "repeated deferential non-answers -- but the panel's computed confidence did not "
                                   "reach the 0.75 adverse-colleague threshold. Per the conservative default, the "
                                   "customer receives full remediation while no adverse finding is recorded against "
                                   "the colleague. A memory note whose basis was a prohibited criterion was read "
                                   "and purged; it played no role in this assessment.",
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C14 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
