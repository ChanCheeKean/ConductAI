"""LangGraph implementation of the neutral AgentRuntime contract."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, RunResult, TerminationReason
from conductai.harness import ArtifactHarness
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.runtime.contracts import RunHandle, RunRequest, RuntimeEvent
from conductai.runtime.workflow import WorkflowDispatcher


class GraphState(TypedDict, total=False):
    run_id: str
    review_id: str
    scenario_id: str
    interaction_ids: list[str]
    trigger: dict[str, Any]
    virtual_now: str
    tool_calls_used: int
    route_facts: dict[str, Any]
    route: dict[str, Any]
    route_event_seq: int
    plan: list[str]
    plan_event_seq: int
    hypothesis_event_seqs: list[int]
    integrity_event_seqs: list[int]
    gather_event_seqs: list[int]
    reroute_reason: str
    evidence: dict[str, Any]
    artifact_needed: bool
    artifact_request: dict[str, Any]
    latest_safe_decision: str
    deadline_event_seq: int
    wait_event_seqs: list[int]
    resume_payload: dict[str, Any]
    artifact: dict[str, Any]
    artifact_event_seqs: list[int]
    expected_inquiry: str
    actual_inquiry: str
    computation_seq: int
    reconcile_event_seq: int
    desktop_offset_s: float
    waiver_true_utc: str
    seconds_before_mention: int
    seconds_before_pitch: int
    root_cause_changed: bool
    reroute_event_seqs: list[int]
    reconcile_event_seqs: list[int]
    population_count: int
    excluded_count: int
    population_colleagues: list[str]
    population_seqs: list[int]
    memory_reject_seq: int
    memory_ops_event_seqs: list[int]
    memory_read_seq: int
    firm_offer_displayed: bool
    firm_offer_valid: bool
    retrieval_decision_seq: int
    fee_at_submitted_rate: str
    fee_at_stated_rate: str
    remediation_amount: str
    verifier_checks: dict[str, bool]
    verification_seqs: list[int]
    computed_confidence: float
    recovered_transcript_quality: float
    panel_used: bool
    panel_reason: str
    panel_event_seqs: list[int]
    finding_event_seq: int
    authorized_actions: list[dict[str, Any]]
    memory_event_seq: int
    assessment: dict[str, Any]
    assessment_event_seq: int
    termination: str | None
    status: str


class LangGraphRuntime:
    def __init__(
        self, root: Path, config: ResolvedConfig, ledger: EventLedger,
        workflow: WorkflowDispatcher, checkpoint_path: Path, harness: ArtifactHarness,
    ) -> None:
        self._root = root
        self._config = config
        self._ledger = ledger
        self._workflow = workflow
        self._harness = harness
        self._requests: dict[str, RunRequest] = {}
        self._results: dict[str, GraphState] = {}
        self._checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self._checkpointer = SqliteSaver(self._checkpoint_connection)
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(GraphState)
        functions = {
            "intake": self._workflow.intake,
            "route": self._workflow.route,
            "fast_path_gather": self._workflow.fast_path_gather,
            "integrity": self._workflow.integrity,
            "request_artifact": self._workflow.request_artifact,
            "prepare_wait": self._workflow.prepare_wait,
            "wait_external": self._wait_external,
            "ingest_artifact": self._workflow.ingest_artifact,
            "gather": self._workflow.gather,
            "reconcile": self._workflow.reconcile,
            "reroute": self._workflow.reroute,
            "preverify": self._workflow.preverify,
            "panel_gate": self._workflow.panel_gate,
            "decide": self._workflow.decide,
            "action": self._workflow.action,
            "memory": self._workflow.memory,
            "record": self._workflow.record,
            "termination": self._workflow.termination,
        }
        for name, function in functions.items():
            builder.add_node(name, function if name == "wait_external" else self._instrument_node(name, function))
        builder.add_edge(START, "intake")
        builder.add_conditional_edges("intake", self._fixed_edge("intake", "route"))
        builder.add_conditional_edges("route", self._route_edge)
        builder.add_conditional_edges("fast_path_gather", self._fixed_edge("fast_path_gather", "reconcile"))
        builder.add_conditional_edges("integrity", self._integrity_edge)
        builder.add_conditional_edges("request_artifact", self._fixed_edge("request_artifact", "prepare_wait"))
        builder.add_conditional_edges("prepare_wait", self._fixed_edge("prepare_wait", "wait_external"))
        builder.add_conditional_edges("wait_external", self._fixed_edge("wait_external", "ingest_artifact"))
        builder.add_conditional_edges("ingest_artifact", self._fixed_edge("ingest_artifact", "integrity", back_edge=True))
        builder.add_conditional_edges("gather", self._fixed_edge("gather", "reconcile"))
        builder.add_conditional_edges("reconcile", self._reconcile_edge)
        builder.add_conditional_edges("reroute", self._fixed_edge("reroute", "integrity", back_edge=True))
        builder.add_conditional_edges("preverify", self._fixed_edge("preverify", "panel_gate"))
        builder.add_conditional_edges("panel_gate", self._fixed_edge("panel_gate", "decide"))
        builder.add_conditional_edges("decide", self._fixed_edge("decide", "action"))
        builder.add_conditional_edges("action", self._fixed_edge("action", "memory"))
        builder.add_conditional_edges("memory", self._fixed_edge("memory", "record"))
        builder.add_conditional_edges("record", self._fixed_edge("record", "termination"))
        builder.add_conditional_edges("termination", self._fixed_edge("termination", END, label="END"))
        return builder.compile(checkpointer=self._checkpointer)

    def _instrument_node(
        self, name: str, function: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def wrapped(state: dict[str, Any]) -> dict[str, Any]:
            virtual_now = _parse(state["virtual_now"])
            before_hash = _state_hash(state)
            entered = self._ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=virtual_now,
                actor=Actor(kind="graph_node", name=name), type=EventType.NODE_ENTERED,
                summary=f"Entered graph node {name}", payload={"node": name, "state_hash": before_hash},
            )
            patch = function(state)
            after = {**state, **patch}
            diff_blob = self._ledger.put_blob(patch)
            self._ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"],
                virtual_now=_parse(after.get("virtual_now", state["virtual_now"])),
                actor=Actor(kind="graph_node", name=name), type=EventType.NODE_EXITED,
                summary=f"Exited graph node {name}",
                payload={"node": name, "diff_blob": diff_blob, "status": "ok"}, span_id=entered.span_id,
            )
            checkpoint_id = f"CP-{state['run_id']}-{name}-{uuid.uuid4()}"
            self._ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"],
                virtual_now=_parse(after.get("virtual_now", state["virtual_now"])),
                actor=Actor(kind="runtime", name="langgraph_checkpointer"), type=EventType.CHECKPOINT_SAVED,
                summary=f"Checkpointed state after {name}",
                payload={"checkpoint_id": checkpoint_id, "state_hash": _state_hash(after)},
                checkpoint_id=checkpoint_id,
            )
            return patch

        return wrapped

    def _fixed_edge(self, source: str, target: str, *, back_edge: bool = False, label: str | None = None):
        def route(state: GraphState) -> str:
            target_label = label or target
            self._emit_edge(state, source, target_label, "mandatory_sequence", True, back_edge)
            if source == "termination":
                digest = hashlib.sha256(json.dumps(state["assessment"], sort_keys=True).encode()).hexdigest()
                self._ledger.emit(
                    run_id=state["run_id"], review_id=state["review_id"], virtual_now=_parse(state["virtual_now"]),
                    actor=Actor(kind="runtime", name="termination_gate"), type=EventType.TERMINATION,
                    summary="Review completed after all mandatory checks passed",
                    payload={"reason": "assessment_complete", "final_state_hash": f"sha256:{digest}"},
                    refs=[state["review_id"]],
                )
            return target

        return route

    def _route_edge(self, state: GraphState) -> str:
        target = "fast_path_gather" if state["route"]["path"] == "fast_clean" else "integrity"
        self._emit_edge(state, "route", target, "route.path", state["route"]["path"], False)
        return target

    def _integrity_edge(self, state: GraphState) -> str:
        target = "request_artifact" if state.get("artifact_needed") else "gather"
        self._emit_edge(state, "integrity", target, "artifact_needed", bool(state.get("artifact_needed")), False)
        return target

    def _reconcile_edge(self, state: GraphState) -> str:
        target = "reroute" if state.get("root_cause_changed") else "preverify"
        self._emit_edge(state, "reconcile", target, "root_cause_changed", bool(state.get("root_cause_changed")), False)
        return target

    def _emit_edge(
        self, state: GraphState, source: str, target: str, condition: str, value: Any, back_edge: bool,
    ) -> None:
        self._ledger.emit(
            run_id=state["run_id"], review_id=state["review_id"], virtual_now=_parse(state["virtual_now"]),
            actor=Actor(kind="graph_node", name=source), type=EventType.EDGE_TAKEN,
            summary=f"Took graph edge {source} to {target}",
            payload={"from": source, "to": target, "condition": condition,
                     "value": value, "back_edge": back_edge},
        )

    @staticmethod
    def _wait_external(state: GraphState) -> dict[str, Any]:
        resumed = interrupt({
            "artifact_id": state["artifact_request"]["artifact_id"],
            "expected_at": state["artifact_request"]["expected_at"],
            "latest_safe_decision": state["latest_safe_decision"],
        })
        return {"resume_payload": resumed, "virtual_now": resumed["virtual_now"]}

    def start(self, request: RunRequest) -> RunHandle:
        run_id = f"RUN-{uuid.uuid4()}"
        self._requests[run_id] = request
        virtual_now = _parse(request.virtual_now)
        self._ledger.emit(
            run_id=run_id, review_id=request.review_id, virtual_now=virtual_now,
            actor=Actor(kind="runtime", name="langgraph_runtime"), type=EventType.RUN_STARTED,
            summary=f"Started {request.scenario_id} review",
            payload={"scenario": request.scenario_id, "snapshot_hash": self._config.snapshot_hash,
                     "resolved_config": self._config.secret_free_snapshot()}, refs=request.interaction_ids,
        )
        return RunHandle(run_id=run_id, review_id=request.review_id)

    def run_or_stream(self, handle: RunHandle) -> Iterator[RuntimeEvent]:
        request = self._requests[handle.run_id]
        initial: GraphState = {
            "run_id": handle.run_id, "review_id": request.review_id, "scenario_id": request.scenario_id,
            "interaction_ids": request.interaction_ids, "trigger": request.trigger,
            "virtual_now": request.virtual_now, "tool_calls_used": 0, "status": "running",
        }
        before = len(self._ledger.events(handle.run_id))
        self._graph.invoke(initial, config=self._thread_config(handle.run_id))
        self._capture_state(handle.run_id)
        yield from self._events_after(handle.run_id, before)

    def resume(self, run_id: str) -> Iterator[RuntimeEvent]:
        snapshot = self._graph.get_state(self._thread_config(run_id))
        state = dict(snapshot.values)
        if state.get("status") != "suspended" or not snapshot.interrupts:
            raise RuntimeError(f"run is not suspended: {run_id}")
        before = len(self._ledger.events(run_id))
        release = self._harness.release_next(run_id)
        old_now = _parse(state["virtual_now"])
        new_now = _parse(release["virtual_now"])
        self._ledger.emit(
            run_id=run_id, review_id=state["review_id"], virtual_now=new_now,
            actor=Actor(kind="harness", name="virtual_clock"), type=EventType.CLOCK_ADVANCED,
            summary="Advanced virtual clock to the next allowed artifact arrival or deadline",
            payload={"from": _iso(old_now), "to": _iso(new_now),
                     "reason": "artifact_arrival" if release["arrived"] else "latest_safe_decision"},
            refs=[release["artifact_id"]],
        )
        checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id", "unknown")
        self._ledger.emit(
            run_id=run_id, review_id=state["review_id"], virtual_now=new_now,
            actor=Actor(kind="runtime", name="langgraph_checkpointer"), type=EventType.CHECKPOINT_RESTORED,
            summary="Restored suspended LangGraph checkpoint",
            payload={"checkpoint_id": checkpoint_id, "resume_reason": "external_event"},
            checkpoint_id=str(checkpoint_id), refs=[release["artifact_id"]],
        )
        self._graph.invoke(Command(resume=release), config=self._thread_config(run_id))
        self._capture_state(run_id)
        self._harness.acknowledge_release(run_id, release["artifact_id"], release["virtual_now"])
        yield from self._events_after(run_id, before)

    def result(self, run_id: str) -> RunResult:
        state = self._results.get(run_id)
        if state is None:
            state = dict(self._graph.get_state(self._thread_config(run_id)).values)
        events = self._ledger.events(run_id)
        assessment = state.get("assessment") or self._ledger.assessment(run_id)
        status = state.get("status", "failed")
        termination = state.get("termination") or ("waiting_external" if status == "suspended" else "error")
        return RunResult(
            run_id=run_id, review_id=state["review_id"], status=status,
            termination=TerminationReason(termination),
            assessment=AssessmentRecord.model_validate(assessment) if assessment else None,
            event_count=len(events), final_event_hash=events[-1].event_hash, completed_at=datetime.now(UTC),
        )

    def cancel(self, run_id: str, reason: str) -> None:
        state = dict(self._graph.get_state(self._thread_config(run_id)).values)
        self._ledger.emit(
            run_id=run_id, review_id=state["review_id"], virtual_now=_parse(state["virtual_now"]),
            actor=Actor(kind="runtime", name="langgraph_runtime"), type=EventType.CANCELLED,
            summary="Run cancelled", payload={"reason": reason},
        )

    def _capture_state(self, run_id: str) -> None:
        self._results[run_id] = dict(self._graph.get_state(self._thread_config(run_id)).values)

    def _events_after(self, run_id: str, before: int) -> Iterator[RuntimeEvent]:
        for event in self._ledger.events(run_id)[before:]:
            yield RuntimeEvent(type=event.type.value, payload=event.model_dump(mode="json"))

    @staticmethod
    def _thread_config(run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": run_id}}


def _state_hash(state: dict[str, Any]) -> str:
    content = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
