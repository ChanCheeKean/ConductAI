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

from conductai.config import ResolvedConfig
from conductai.domain.models import Actor, AssessmentRecord, RunResult, TerminationReason
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.runtime.c03_workflow import C03Workflow
from conductai.runtime.contracts import RunHandle, RunRequest, RuntimeEvent


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
    evidence: dict[str, Any]
    expected_inquiry: str
    actual_inquiry: str
    computation_seq: int
    verifier_checks: dict[str, bool]
    verification_seqs: list[int]
    panel_used: bool
    panel_reason: str
    finding_event_seq: int
    authorized_actions: list[dict[str, Any]]
    memory_event_seq: int
    assessment: dict[str, Any]
    assessment_event_seq: int
    termination: str
    status: str


class LangGraphRuntime:
    def __init__(self, root: Path, config: ResolvedConfig, ledger: EventLedger,
                 workflow: C03Workflow, checkpoint_path: Path) -> None:
        self._root = root
        self._config = config
        self._ledger = ledger
        self._workflow = workflow
        self._requests: dict[str, RunRequest] = {}
        self._results: dict[str, GraphState] = {}
        self._checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self._checkpointer = SqliteSaver(self._checkpoint_connection)
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(GraphState)
        nodes: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
            ("intake", self._workflow.intake), ("route", self._workflow.route),
            ("fast_path_gather", self._workflow.fast_path_gather), ("reconcile", self._workflow.reconcile),
            ("preverify", self._workflow.preverify), ("panel_gate", self._workflow.panel_gate),
            ("decide", self._workflow.decide), ("action", self._workflow.action),
            ("memory", self._workflow.memory), ("record", self._workflow.record),
            ("termination", self._workflow.termination),
        ]
        next_names = [name for name, _ in nodes[1:]] + ["END"]
        for (name, function), next_name in zip(nodes, next_names, strict=True):
            builder.add_node(name, self._instrument_node(name, next_name, function))
        builder.add_edge(START, "intake")
        for (source, _), (target, _) in zip(nodes, nodes[1:]):
            builder.add_edge(source, target)
        builder.add_edge("termination", END)
        return builder.compile(checkpointer=self._checkpointer)

    def _instrument_node(self, name: str, next_name: str, function: Callable[[dict[str, Any]], dict[str, Any]]):
        def wrapped(state: dict[str, Any]) -> dict[str, Any]:
            virtual_now = datetime.fromisoformat(state["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)
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
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=virtual_now,
                actor=Actor(kind="graph_node", name=name), type=EventType.NODE_EXITED,
                summary=f"Exited graph node {name}", payload={"node": name, "diff_blob": diff_blob, "status": "ok"},
                span_id=entered.span_id,
            )
            checkpoint_id = f"CP-{state['run_id']}-{name}"
            self._ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=virtual_now,
                actor=Actor(kind="runtime", name="langgraph_checkpointer"), type=EventType.CHECKPOINT_SAVED,
                summary=f"Checkpointed state after {name}",
                payload={"checkpoint_id": checkpoint_id, "state_hash": _state_hash(after)},
                checkpoint_id=checkpoint_id,
            )
            self._ledger.emit(
                run_id=state["run_id"], review_id=state["review_id"], virtual_now=virtual_now,
                actor=Actor(kind="graph_node", name=name), type=EventType.EDGE_TAKEN,
                summary=f"Took graph edge {name} to {next_name}",
                payload={"from": name, "to": next_name, "condition": "mandatory_sequence",
                         "value": True, "back_edge": False},
            )
            if name == "termination":
                digest = hashlib.sha256(json.dumps(after["assessment"], sort_keys=True).encode()).hexdigest()
                self._ledger.emit(
                    run_id=state["run_id"], review_id=state["review_id"], virtual_now=virtual_now,
                    actor=Actor(kind="runtime", name="termination_gate"), type=EventType.TERMINATION,
                    summary="Review completed after all mandatory checks passed",
                    payload={"reason": "assessment_complete", "final_state_hash": f"sha256:{digest}"},
                    refs=[state["review_id"]],
                )
            return patch
        return wrapped

    def start(self, request: RunRequest) -> RunHandle:
        run_id = f"RUN-{uuid.uuid4()}"
        self._requests[run_id] = request
        virtual_now = datetime.fromisoformat(request.virtual_now.replace("Z", "+00:00")).astimezone(UTC)
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
            "virtual_now": request.virtual_now, "tool_calls_used": 0,
        }
        result = self._graph.invoke(initial, config={"configurable": {"thread_id": handle.run_id}})
        self._results[handle.run_id] = result
        for event in self._ledger.events(handle.run_id):
            yield RuntimeEvent(type=event.type.value, payload=event.model_dump(mode="json"))

    def result(self, run_id: str) -> RunResult:
        state = self._results[run_id]
        events = self._ledger.events(run_id)
        return RunResult(
            run_id=run_id, review_id=state["review_id"], status=state["status"],
            termination=TerminationReason(state["termination"]),
            assessment=AssessmentRecord.model_validate(state["assessment"]), event_count=len(events),
            final_event_hash=events[-1].event_hash, completed_at=datetime.now(UTC),
        )

    def cancel(self, run_id: str, reason: str) -> None:
        request = self._requests[run_id]
        self._ledger.emit(
            run_id=run_id, review_id=request.review_id,
            virtual_now=datetime.fromisoformat(request.virtual_now.replace("Z", "+00:00")),
            actor=Actor(kind="runtime", name="langgraph_runtime"), type=EventType.CANCELLED,
            summary="Run cancelled", payload={"reason": reason},
        )


def _state_hash(state: dict[str, Any]) -> str:
    content = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
