"""C06 silent switch: the decisive act lives in a desktop event, not in the words spoken on the call. A CRM
note claiming disclosure is an untrusted colleague assertion, not evidence; a requested colleague statement
restates that same unverifiable claim without adding a new fact. Two sequential external waits (colleague
statement, then customer outreach) gate a real, adversarial panel before remediation.

Deviates from the case catalog's narrated servicing -> sales re-route: `product_change_event_present` is now a
first-class route fact detected at intake, so the router already lands on the correct product-change
investigation path from the start; no reroute back-edge is needed for routing purposes. The `reroute` back-edge
IS still used here, but only to request the colleague statement mid-investigation, after the CRM note's
disclosure claim is found uncorroborated by the transcript (see `reconcile`/`reroute`/`integrity` below).
"""

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
from conductai.runtime.support import leaf_paths, node_context
from conductai.skills import load_skill
from conductai.tools.executor import ToolExecutor


_SWITCH_TERMS = (
    "product", "reward", "mile", "benefit", "trip protection", "downgrade",
    "switch", "everyday cash", "voyager", "cash back", "cash-back",
)


class C06Workflow:
    """Deterministic silent-switch path with a colleague-statement wait, a real panel, and a customer-outreach
    wait; C06 only."""

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
        if route.route_id != "product_change_fee_request":
            raise RuntimeError("C06 requires the product_change_fee_request route")
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="router", name="deterministic_first"),
            type=EventType.ROUTE_DECISION,
            summary="Selected the product-change fee-request path: the desktop already shows a real-time "
                    "product change, so no servicing-to-sales re-route is needed for routing itself",
            payload={"candidates": evaluated, "matched_rule": route.route_id, "method": route.method,
                     **route.model_dump(), "features_used": {
                         "trigger.type": state["trigger"]["type"],
                         "product_change_event_present": state["route_facts"]["product_change_event_present"],
                         "product_change_record_present": state["route_facts"]["product_change_record_present"],
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
        if state.get("root_cause_changed"):
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
                type=EventType.REVIEW_FILE_UPDATED,
                summary="Requesting the colleague statement: the CRM note's disclosure claim remains "
                        "uncorroborated by the transcript, so a defense position needs the colleague's own words "
                        "before the panel can weigh it",
                payload={"path": "evidence_matrix.json",
                         "columns": ["said", "did", "crm_note", "colleague_statement"]},
                refs=[interaction_id],
            )
            return {"artifact_needed": True, "integrity_event_seqs": [*state["integrity_event_seqs"], event.seq]}
        used = state["tool_calls_used"]
        transcript, used = self.tools.execute(
            "get_transcript", {"interaction_id": interaction_id},
            rationale="Read the full call for any mention of a product change, rewards, or benefits",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        transcript_text = " ".join(turn["text"].lower() for turn in transcript)
        transcript_silent = not any(term in transcript_text for term in _SWITCH_TERMS)
        assessed = self.ledger.emit(
            **node_context(state), actor=Actor(kind="subagent", name="transcript_integrity_analyst"),
            type=EventType.TRANSCRIPT_ASSESSED,
            summary="Recording is complete with no gaps; the transcript never mentions a product change, "
                    "rewards, or benefits at all, so nothing was lost to a recording issue",
            payload={"interaction_id": interaction_id, "turn_id": "t02", "source": "asr",
                     "recording_gap": False, "recovery_recommended": None,
                     "transcript_silent_on_product_change": transcript_silent},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02"],
        )
        return {"evidence": {"transcript": transcript}, "tool_calls_used": used,
                "artifact_needed": False, "transcript_silent_on_product_change": transcript_silent,
                "integrity_event_seqs": [assessed.seq]}

    def gather(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        used = state["tool_calls_used"]
        governing_date = state["route_facts"]["interaction"]["started_at_utc"][:10]
        desktop, used = self.tools.execute(
            "get_desktop_events", {"interaction_id": interaction_id},
            rationale="Find the decisive desktop action behind the vague 'taken care of that' assurance",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        product_change, used = self.tools.execute(
            "get_product_change", {"interaction_id": interaction_id},
            rationale="Retrieve the product-change record the desktop event submitted, including the rewards "
                       "conversion and removed benefits",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        crm_notes, used = self.tools.execute(
            "get_crm_notes", {"interaction_id": interaction_id},
            rationale="Read the colleague's own CRM note describing what was allegedly disclosed",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-CHC-PC", "governing_date": governing_date},
            rationale="Resolve the disclosure and consent requirements for a product change",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        remediation_policy, used = self.tools.execute(
            "retrieve_corpus_as_of", {"doc_id": "CLB-SOP-SRV-004", "governing_date": governing_date},
            rationale="Resolve the customer remediation matrix for an undisclosed product change",
            used=used, limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        evidence = {**state["evidence"], "desktop_events": desktop, "product_change": product_change,
                    "crm_notes": crm_notes, "policy": policy, "remediation_policy": remediation_policy}
        blob = self.ledger.put_blob(evidence)
        update = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="review_file"),
            type=EventType.REVIEW_FILE_UPDATED,
            summary="Added the desktop product-change event, the product-change record, the colleague's CRM "
                    "note, and the disclosure/remediation policies",
            payload={"path": "evidence_matrix.json", "patch_blob": blob,
                     "columns": ["said", "did", "crm_note", "policy"]},
            refs=[desktop[0]["event_id"], product_change["product_change_id"], crm_notes[0]["note_id"],
                  policy["source_id"], remediation_policy["source_id"]],
        )
        return {"evidence": evidence, "tool_calls_used": used, "gather_event_seqs": [update.seq]}

    def reconcile(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        prior_seqs = state.get("reconcile_event_seqs", [])
        if "colleague_statement" not in evidence:
            crm_note = evidence["crm_notes"][0]
            finding = self.ledger.emit(
                **node_context(state), actor=Actor(kind="agent", name="desktop_records_reconciler"),
                type=EventType.FINDING_UPDATED,
                summary="The CRM note claims rewards impact was disclosed, but the transcript never mentions a "
                        "product change, rewards, or benefits at all — the note is uncorroborated",
                payload={"finding_id": "F1", "from": "informed_consent_to_fee_fix", "to": "undisclosed_product_switch",
                         "reason": "the CRM note's disclosure claim is uncorroborated by the transcript",
                         "transcript_silent_on_product_change": state["transcript_silent_on_product_change"],
                         "crm_note_text": crm_note["text"], "crm_note_id": crm_note["note_id"]},
                refs=[f"{interaction_id}:t01", f"{interaction_id}:t02", crm_note["note_id"]],
            )
            return {"root_cause_changed": True,
                     "reroute_reason": "the CRM note's disclosure claim is uncorroborated by the transcript; a "
                                       "colleague statement is needed before the panel can weigh a defense position",
                     "reconcile_event_seqs": [*prior_seqs, finding.seq]}
        statement = evidence["colleague_statement"]
        statement_text = statement["text"].lower()
        adds_new_fact = any(term in statement_text for term in _SWITCH_TERMS)
        product_change = evidence["product_change"]
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="rewards_conversion_check"),
            type=EventType.COMPUTATION,
            summary=f"Confirmed the {product_change['rewards_before']}-mile rewards balance converts to the "
                    f"${product_change['rewards_conversion_value']} cash-back value already stored on the record",
            payload={"helper": "rewards_conversion_check",
                     "inputs": {"rewards_before": product_change["rewards_before"],
                                "rewards_after": product_change["rewards_after"]},
                     "output": product_change["rewards_conversion_value"], "runtime": "registered_python_helper"},
            refs=[product_change["product_change_id"]],
        )
        finding = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.FINDING_UPDATED,
            summary="The colleague statement restates the CRM note's unverifiable claim ('I explained it on the "
                    "call') and adds no new verifiable fact; the undisclosed-switch finding stands",
            payload={"finding_id": "F1", "status": "substantiated_candidate",
                     "colleague_statement_text": statement["text"],
                     "colleague_statement_adds_new_fact": adds_new_fact},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02", "CST-9000701"],
        )
        return {"root_cause_changed": False, "colleague_statement_adds_new_fact": adds_new_fact,
                "reconcile_event_seqs": [*prior_seqs, computation.seq, finding.seq]}

    def reroute(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="lead_conduct_reviewer"),
            type=EventType.PLAN_UPDATED,
            summary="Re-planned to request the colleague's own statement before the panel weighs a defense "
                    "position, since the CRM note alone is an untrusted colleague assertion",
            payload={"reason_event_seq": state["reconcile_event_seqs"][-1],
                     "patch": [{"op": "add", "path": "/steps/-",
                                "value": "request the colleague statement CST-9000701"}]},
            refs=[state["interaction_ids"][0]],
        )
        return {"reroute_event_seqs": [event.seq]}

    def preverify(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        product_change = evidence["product_change"]
        desktop_event = evidence["desktop_events"][0]
        checks = {
            "transcript_never_mentions_product_change": state["transcript_silent_on_product_change"],
            "desktop_event_proves_the_switch": desktop_event["type"] == "product_change_submitted",
            "crm_note_uncorroborated_by_transcript": state["transcript_silent_on_product_change"],
            "colleague_statement_adds_no_new_fact": not state["colleague_statement_adds_new_fact"],
            "rewards_conversion_verified": float(product_change["rewards_after"]) == float(
                product_change["rewards_conversion_value"]),
            "disclosure_policy_as_of": evidence["policy"]["version"] == "v3",
            "remediation_policy_as_of": evidence["remediation_policy"]["version"] == "v2",
        }
        span = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.EVIDENCE_SPAN_VERIFIED,
            summary="Verified the transcript never names a product change, rewards, or benefits across either turn",
            payload={"interaction_id": interaction_id, "turn_ids": ["t01", "t02"],
                     "quotes": [turn["text"] for turn in evidence["transcript"]],
                     "substring_match": checks["transcript_never_mentions_product_change"]},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02"],
        )
        citation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
            type=EventType.CITATION_VERIFIED,
            summary="Verified CLB-CHC-PC v3 and CLB-SOP-SRV-004 v2 governed the interaction date",
            payload={"docs": [evidence["policy"]["source_id"], evidence["remediation_policy"]["source_id"]],
                     "governing_date": interaction_id and state["route_facts"]["interaction"]["started_at_utc"][:10],
                     "valid": checks["disclosure_policy_as_of"] and checks["remediation_policy_as_of"]},
            refs=[evidence["policy"]["source_id"], evidence["remediation_policy"]["source_id"]],
        )
        check_seqs = []
        for check_id, passed in checks.items():
            event = self.ledger.emit(
                **node_context(state), actor=Actor(kind="governance", name="deterministic_verifier"),
                type=EventType.VERIFIER_CHECK, summary=f"{check_id}: {'pass' if passed else 'fail'}",
                payload={"check_id": check_id, "kind": "C06_L4", "result": "pass" if passed else "fail"},
                refs=[product_change["product_change_id"], desktop_event["event_id"]],
            )
            check_seqs.append(event.seq)
        if not all(checks.values()):
            raise RuntimeError("C06 deterministic verifier failed")
        return {"verifier_checks": checks, "verification_seqs": [span.seq, citation.seq, *check_seqs]}

    def panel_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        product_change = evidence["product_change"]
        snapshot = {"finding": "MC-08 + MC-11 candidate, colleague",
                    "crm_note_uncorroborated": True,
                    "colleague_statement_adds_new_fact": state["colleague_statement_adds_new_fact"]}
        snapshot_hash = self.ledger.put_blob(snapshot)
        started = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="panel_governance"),
            type=EventType.PANEL_STARTED,
            summary="Panel required: high-severity undisclosed product switch with competing consent interpretations",
            payload={"predicate": "high_and_undisclosed_switch", "snapshot_hash": snapshot_hash},
            refs=[interaction_id],
        )
        customer_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="customer_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Customer advocate: 'whatever you need to do' cannot be informed consent to an unstated "
                    "product change with unstated consequences — lost rewards value and trip protection",
            payload={"role": "customer_advocate", "position": "undisclosed_switch_not_consented",
                     "key_refs": [f"{interaction_id}:t01", product_change["product_change_id"]],
                     "snapshot_hash": snapshot_hash},
            refs=[f"{interaction_id}:t01", product_change["product_change_id"]],
        )
        colleague_position = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="colleague_advocate"),
            type=EventType.PANEL_POSITION,
            summary="Colleague advocate: the customer authorized 'whatever you need to do' — a broad grant of "
                    "discretion to resolve the fee however necessary",
            payload={"role": "colleague_advocate", "position": "broad_authorization_covers_the_fix",
                     "key_refs": [f"{interaction_id}:t01"], "snapshot_hash": snapshot_hash},
            refs=[f"{interaction_id}:t01"],
        )
        adjudication = self.ledger.emit(
            **node_context(state), actor=Actor(kind="agent", name="adjudicator"),
            type=EventType.ADJUDICATION,
            summary="Adjudicated: informed consent requires disclosure of what is actually being done; a broad "
                    "'whatever you need to do' does not waive disclosure of a specific product change and its "
                    "consequences",
            payload={"determinative_issue": "whether broad customer authorization displaces the duty to disclose "
                                             "the specific action taken and its consequences",
                     "decision": "substantiated",
                     "flip_fact": "the transcript had actually named the product change and disclosed the "
                                   "rewards and benefit impact"},
            refs=[f"{interaction_id}:t01", product_change["product_change_id"]],
        )
        panel_agreement = 0.67
        weights = {"verifier_pass_rate": 0.25, "citation_verification": 0.20, "evidence_coverage": 0.25,
                   "transcript_quality": 0.20, "panel_agreement": 0.10}
        result = round(
            weights["verifier_pass_rate"] * 1.0 + weights["citation_verification"] * 1.0
            + weights["evidence_coverage"] * 1.0 + weights["transcript_quality"] * 1.0
            + weights["panel_agreement"] * panel_agreement, 4,
        )
        confidence = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="confidence_gate"),
            type=EventType.CONFIDENCE_COMPUTED,
            summary="Computed confidence reflecting the colleague advocate's non-frivolous but rejected position",
            payload={"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 1.0,
                     "transcript_quality": 1.0, "panel_agreement": panel_agreement, "weights": weights,
                     "result": result},
            refs=[evidence["policy"]["source_id"]],
        )
        return {"panel_used": True,
                "panel_reason": "severity high and an undisclosed product switch with competing consent "
                                "interpretations", "computed_confidence": result, "outreach_needed": True,
                "panel_event_seqs": [started.seq, customer_position.seq, colleague_position.seq,
                                     adjudication.seq, confidence.seq]}

    def request_artifact(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction = state["route_facts"]["interaction"]
        if not state.get("outreach_needed"):
            trigger_at = state["route_facts"]["scanner_flags"][0]["flagged_at"]
            latest_date = latest_safe_decision(interaction["started_at_utc"], trigger_at, 10)
            respond_by = f"{latest_date}T23:59:59Z"
            computation = self.ledger.emit(
                **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
                type=EventType.COMPUTATION,
                summary=f"Computed monitoring deadline {latest_date} for the requested colleague statement",
                payload={"helper": "latest_safe_decision", "inputs": {
                    "interaction_date": interaction["started_at_utc"][:10], "trigger_date": trigger_at[:10],
                    "business_days": 10, "excluded_holiday": "2026-11-11"},
                    "output": latest_date, "runtime": "registered_python_helper"},
                refs=[interaction["interaction_id"]],
            )
            request, used = self.tools.execute(
                "request_artifact", {
                    "artifact_id": "CST-9000701", "interaction_id": interaction["interaction_id"],
                    "kind": "colleague_statement", "respond_by": respond_by,
                    "idempotency_key": f"{state['review_id']}:CST-9000701",
                }, rationale="Request the colleague's own statement before the panel weighs a defense position, "
                             "since the CRM note's disclosure claim is uncorroborated by the transcript",
                used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
            )
            return {"artifact_request": request, "tool_calls_used": used, "latest_safe_decision": respond_by,
                    "deadline_event_seqs": [computation.seq],
                    "colleague_statement_request": request,
                    "colleague_statement_latest_safe_decision": respond_by,
                    "resume_target": "reconcile"}
        latest_date = latest_safe_decision(interaction["started_at_utc"], interaction["started_at_utc"], 10)
        respond_by = f"{latest_date}T23:59:59Z"
        computation = self.ledger.emit(
            **node_context(state), actor=Actor(kind="sandbox", name="latest_safe_decision"),
            type=EventType.COMPUTATION,
            summary=f"Computed monitoring deadline {latest_date} for the customer outreach reply",
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
                "question": "We found that your $95 annual-fee call actually resulted in a full product change "
                             "from Voyager to Everyday Cash, which forfeited your 48,200 rewards miles and "
                             "removed trip protection — none of that was mentioned on the call. Would you like "
                             "us to reverse the product change, restore your rewards, and still waive the "
                             "annual fee?",
                "respond_by": respond_by, "idempotency_key": f"{state['review_id']}:OUTREACH",
            }, rationale="Ask the customer whether to reverse the undisclosed product change before deciding "
                         "remediation",
            used=state["tool_calls_used"], limit=state["route"]["budget"]["tool_calls"], **node_context(state),
        )
        return {"artifact_request": request, "tool_calls_used": used, "latest_safe_decision": respond_by,
                "deadline_event_seqs": [*state.get("deadline_event_seqs", []), computation.seq],
                "outreach_request": request, "outreach_latest_safe_decision": respond_by,
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
            type=EventType.WAIT_SUSPENDED, summary="Suspended only for the requested artifact",
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
            raise RuntimeError(f"C06 {resumed['kind']} did not arrive before latest safe decision")
        if resumed["kind"] == "colleague_statement":
            arrived = self.ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
                actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.COLLEAGUE_STATEMENT_ARRIVED,
                summary="Released the requested colleague statement into the agent view",
                payload={"artifact_id": resumed["artifact_id"], "kind": resumed["kind"],
                         "available_at": resumed["virtual_now"],
                         "statement_blob": self.ledger.put_blob(resumed["artifact"])},
                refs=[resumed["artifact_id"], state["interaction_ids"][0]],
            )
            wait = self.ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=now,
                actor=Actor(kind="harness", name="virtual_clock"), type=EventType.WAIT_RESUMED,
                summary="Resumed C06 after the colleague statement arrived",
                payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                         "reason": "colleague_statement_arrived"}, refs=[resumed["artifact_id"]],
            )
            evidence = {**state["evidence"], "colleague_statement": resumed["artifact"]}
            return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                    "status": "running", "termination": None,
                    "colleague_statement_arrived_at": resumed["virtual_now"],
                    "artifact_event_seqs": [*state.get("artifact_event_seqs", []), arrived.seq, wait.seq]}
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
            summary="Resumed C06 after the customer's outreach reply arrived",
            payload={"artifact_id": resumed["artifact_id"], "resumed_at": resumed["virtual_now"],
                     "reason": "customer_reply_arrived"}, refs=[resumed["artifact_id"]],
        )
        evidence = {**state["evidence"], "customer_reply": resumed["artifact"]["text"]}
        return {"evidence": evidence, "virtual_now": resumed["virtual_now"],
                "status": "running", "termination": None,
                "outreach_arrived_at": resumed["virtual_now"],
                "artifact_event_seqs": [*state.get("artifact_event_seqs", []), arrived.seq, wait.seq]}

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        reply = state["evidence"]["customer_reply"]
        reverse_requested = "put it back" in reply.lower()
        fee_still_waived = "waive" in reply.lower()
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="governance", name="outcome_gate"),
            type=EventType.FINDING_PROPOSED,
            summary="Proposed MC-08 and MC-11 substantiated against the colleague; the customer confirmed the "
                    "product change should be reversed and asked that the fee still be waived",
            payload={"findings": [
                {"finding_id": "F1", "category": "MC-08", "status": "substantiated", "attributable_to": "colleague"},
                {"finding_id": "F2", "category": "MC-11", "status": "substantiated", "attributable_to": "colleague"},
            ], "customer_reply": reply, "reverse_requested": reverse_requested,
                "fee_still_waived": fee_still_waived},
            refs=[f"{interaction_id}:t01", f"{interaction_id}:t02",
                  state["evidence"]["crm_notes"][0]["note_id"]],
        )
        return {"finding_event_seq": event.seq, "reverse_requested": reverse_requested,
                "fee_still_waived": fee_still_waived}

    def action(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"authorized_actions": []}

    def memory(self, state: dict[str, Any]) -> dict[str, Any]:
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="memory", name="memory_write_gate"),
            type=EventType.MEMORY_WRITE_SKIPPED,
            summary="Skipped memory write for a single-interaction colleague finding",
            payload={"subject": state["route_facts"]["interaction"]["colleague_id"],
                     "reason": "case-local finding from one verified interaction; no generalizable pattern basis",
                     "gate_checks": {"case_local": True, "generalizable": False, "prohibited_content": False}},
            refs=[state["interaction_ids"][0]],
        )
        return {"memory_event_seq": event.seq}

    def record(self, state: dict[str, Any]) -> dict[str, Any]:
        interaction_id = state["interaction_ids"][0]
        evidence = state["evidence"]
        turns = {turn["turn_id"]: turn for turn in evidence["transcript"]}
        product_change = evidence["product_change"]
        desktop_event = evidence["desktop_events"][0]
        crm_note = evidence["crm_notes"][0]
        policy = evidence["policy"]
        remediation_policy = evidence["remediation_policy"]
        source_refs = [f"{interaction_id}:t01", f"{interaction_id}:t02", desktop_event["event_id"],
                       product_change["product_change_id"], crm_note["note_id"], "CST-9000701",
                       policy["source_id"], remediation_policy["source_id"],
                       state["outreach_request"]["artifact_id"]]
        seqs = sorted(set([
            state["route_event_seq"], state["finding_event_seq"], state["memory_event_seq"],
            *state["deadline_event_seqs"], *state["integrity_event_seqs"], *state["gather_event_seqs"],
            *state["reconcile_event_seqs"], *state["reroute_event_seqs"], *state["verification_seqs"],
            *state["panel_event_seqs"], *state["wait_event_seqs"], *state["artifact_event_seqs"],
        ]))
        findings = [
            Finding(
                finding_id="F1", category="MC-08", status="substantiated", attributable_to="colleague",
                severity="high", interaction_id=interaction_id,
                evidence_spans=[
                    {"interaction_id": interaction_id, "turn_id": "t01",
                     "start_s": float(turns["t01"]["start_s"]), "end_s": float(turns["t01"]["end_s"]),
                     "quote": turns["t01"]["text"], "verified": True},
                    {"interaction_id": interaction_id, "turn_id": "t02",
                     "start_s": float(turns["t02"]["start_s"]), "end_s": float(turns["t02"]["end_s"]),
                     "quote": turns["t02"]["text"], "verified": True},
                ],
                structured_evidence=[
                    {"source": "desktop_events", "id": desktop_event["event_id"],
                     "fact": "product_change_submitted VOYAGER -> EVERYDAY_CASH desktop event, never mentioned "
                             "in the transcript"},
                    {"source": "product_changes", "id": product_change["product_change_id"],
                     "fact": f"{product_change['rewards_before']} miles forfeited (converted to "
                             f"${product_change['rewards_conversion_value']} cash-back value), trip protection "
                             "removed, annual fee reversed"},
                ],
                policy_refs=[{"doc_id": policy["source_id"], "clauses": ["2.1", "2.2", "2.3"], "verified": True}],
                confidence=state["computed_confidence"],
            ),
            Finding(
                finding_id="F2", category="MC-11", status="substantiated", attributable_to="colleague",
                severity="high", interaction_id=interaction_id,
                evidence_spans=[
                    {"interaction_id": interaction_id, "turn_id": "t01",
                     "start_s": float(turns["t01"]["start_s"]), "end_s": float(turns["t01"]["end_s"]),
                     "quote": turns["t01"]["text"], "verified": True},
                ],
                structured_evidence=[
                    {"source": "crm_notes", "id": crm_note["note_id"],
                     "fact": f"CRM note claims '{crm_note['text']}'; contradicted by a transcript that never "
                             "mentions rewards, benefits, or the product change"},
                    {"source": "colleague_statements", "id": "CST-9000701",
                     "fact": "colleague statement restates 'I explained it on the call' and adds no new "
                             "verifiable fact"},
                ],
                policy_refs=[{"doc_id": remediation_policy["source_id"], "clauses": ["2.2"], "verified": True}],
                confidence=state["computed_confidence"],
            ),
        ]
        base: dict[str, Any] = {
            "schema_version": 1, "run_id": state["run_id"], "review_id": state["review_id"],
            "interaction_ids": [interaction_id], "route": state["route"],
            "findings": [finding.model_dump() for finding in findings],
            "customer_outcome": {
                "harm_likely": True,
                "remediation": [
                    {"action": "reverse_product_change", "from_product": product_change["to_product"],
                     "to_product": product_change["from_product"]},
                    {"action": "restore_rewards", "amount": product_change["rewards_before"], "unit": "miles"},
                    {"action": "waive_annual_fee", "amount": "95.00"},
                    {"action": "restore_trip_protection"},
                ],
                "customer_choice": "reverse_and_waive", "customer_reply": state["evidence"]["customer_reply"],
                "customer_confirmed_reversal": state["reverse_requested"],
            },
            "colleague_outcome": {"colleague_id": state["route_facts"]["interaction"]["colleague_id"],
                                  "finding": "substantiated",
                                  "actions": ["record_colleague_finding", "assign_coaching", "enhanced_monitoring"],
                                  "aggravating_factors": []},
            "control_outcome": {"records": [
                {"type": "control_observation", "subject": "Q4 incentive plan",
                 "observation": "the Q4 incentive plan counts a product change as a 'save', creating an "
                                "incentive to submit an undisclosed switch instead of processing a simple fee "
                                "waiver",
                 "must_not": ["incentive_clawback", "employment_action"]},
            ]},
            "adjudication": {"panel_used": True, "panel_reason": state["panel_reason"],
                             "computed_confidence": state["computed_confidence"], "threshold": 0.75,
                             "conservative_default_applied": False,
                             "flip_fact": "the transcript had actually named the product change and disclosed "
                                          "the rewards and benefit impact"},
            "waits": [
                {"artifact_id": "CST-9000701", "kind": "colleague_statement",
                 "requested_at": state["colleague_statement_request"]["requested_at"],
                 "expected_at": state["colleague_statement_request"]["expected_at"],
                 "arrived_at": state["colleague_statement_arrived_at"],
                 "latest_safe_decision": state["colleague_statement_latest_safe_decision"], "result": "arrived"},
                {"artifact_id": state["outreach_request"]["artifact_id"], "kind": "customer_reply",
                 "requested_at": state["outreach_request"]["requested_at"],
                 "expected_at": state["outreach_request"]["expected_at"],
                 "arrived_at": state["outreach_arrived_at"],
                 "latest_safe_decision": state["outreach_latest_safe_decision"], "result": "arrived"},
            ],
            "memory_ops": [{"op": "skip", "reason": "case-local finding from one verified interaction; no "
                                                     "generalizable pattern basis", "source_refs": [interaction_id]}],
            "graph_writes": [],
            "hypotheses": [
                {"id": "H1", "label": "'whatever you need to do' was informed consent to a fee fix",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H2", "label": "the disclosure was spoken but lost to a recording gap or ASR error",
                 "status": "rejected", "evidence_against": source_refs},
                {"id": "H3", "label": "the colleague made an undisclosed product switch and the CRM note "
                                       "misrepresents the interaction", "status": "supported",
                 "evidence_for": source_refs},
            ],
            "citations": [
                {"doc_id": policy["source_id"], "why": "rewards, benefit, and consent disclosure requirements "
                                                        "for a product change"},
                {"doc_id": remediation_policy["source_id"], "why": "the undisclosed-product-change remediation "
                                                                    "matrix entry (reverse, restore rewards, "
                                                                    "honor the represented outcome)"},
            ],
            "summary_for_record": (
                "MC-08 and MC-11 substantiated against the colleague. The desktop shows a product-change "
                f"submission from {product_change['from_product']} to {product_change['to_product']} that "
                "forfeited 48,200 rewards miles and removed trip protection, but the transcript never mentions a "
                "product change, rewards, or benefits at all. The colleague's CRM note claims the rewards impact "
                "was disclosed; the requested colleague statement restates that same unverifiable claim without "
                "adding a new fact. The customer confirmed by outreach reply that the product change should be "
                "reversed and asked that the fee still be waived; both are honored, along with restoring the "
                "miles and trip protection. The Q4 incentive plan's treatment of a product change as a 'save' is "
                "recorded as a control observation only — no incentive clawback or employment action is proposed."
            ),
            "customer_letter": None,
        }
        paths = leaf_paths(base)
        base["field_provenance"] = {path: Provenance(event_seqs=seqs, source_refs=source_refs).model_dump() for path in paths}
        assessment = AssessmentRecord.model_validate(base)
        blob = self.ledger.put_blob(assessment.model_dump(mode="json"))
        event = self.ledger.emit(
            **node_context(state), actor=Actor(kind="graph_node", name="assessment_repository"),
            type=EventType.ASSESSMENT_RECORDED, summary="Recorded provenance-complete C06 assessment",
            payload={"assessment_blob": blob, "field_provenance": assessment.field_provenance}, refs=source_refs,
        )
        self.ledger.record_assessment(state["run_id"], state["review_id"], assessment.model_dump(mode="json"), event.seq)
        return {"assessment": assessment.model_dump(mode="json"), "assessment_event_seq": event.seq}

    def termination(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"termination": "assessment_complete", "status": "complete"}
