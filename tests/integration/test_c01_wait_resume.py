import sqlite3

from conductai.app import build_runtime
from conductai.observability.replay import replay_assessment


def _leaf_paths(value, prefix=""):
    if isinstance(value, dict):
        paths = []
        for key, item in value.items():
            paths.extend(_leaf_paths(item, f"{prefix}.{key}" if prefix else key))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_leaf_paths(item, f"{prefix}[{index}]"))
        return paths or [prefix]
    return [prefix]


def test_c01_suspends_without_exposing_the_future_artifact(c01_suspended):
    runtime, ledger, handle, path = c01_suspended
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "artifact_requested" in types
    assert "wait_suspended" in types
    assert "artifact_arrived" not in types
    with sqlite3.connect(path) as conn:
        request = conn.execute(
            "SELECT expected_at,latest_safe_decision,released_at FROM artifact_requests WHERE run_id=?",
            (handle.run_id,),
        ).fetchone()
    assert request == ("2026-11-16T19:00:00Z", "2026-11-27T23:59:59Z", None)


def test_c01_resumes_from_a_durable_checkpoint_and_clears_false_positive(
    c01_suspended, project_root,
):
    _, _, handle, path = c01_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    assessment = result.assessment
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "addon_consent_integrity"
    assert assessment.route.depth == "L2"
    assert assessment.findings[0].status == "no_error"
    assert assessment.findings[0].evidence_spans[0]["quote"] == "Oh — I do need that. Go ahead."
    assert assessment.customer_outcome["remediation"] == [{"action": "none"}]
    assert assessment.colleague_outcome["finding"] == "no_finding"
    assert assessment.control_outcome["records"] == []
    assert assessment.waits[0]["requested_at"] == "2026-11-16T15:00:00Z"
    assert assessment.waits[0]["arrived_at"] == "2026-11-16T19:00:00Z"
    assert assessment.waits[0]["latest_safe_decision"].startswith("2026-11-27")
    assert len([event for event in events if event.type.value == "tool_call"]) == 6
    for required in (
        "agent_started", "llm_call_started", "llm_call", "agent_finished",
        "transcript_assessed", "artifact_requested", "wait_suspended", "clock_advanced",
        "checkpoint_restored", "artifact_arrived", "wait_resumed", "contradiction_detected",
        "memory_write_skipped", "termination",
    ):
        assert required in types
    assert any(
        event.type.value == "edge_taken" and event.payload.get("back_edge") is True
        for event in events
    )
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    with sqlite3.connect(path) as conn:
        released_at = conn.execute(
            "SELECT released_at FROM artifact_requests WHERE run_id=?", (handle.run_id,)
        ).fetchone()[0]
    assert released_at == "2026-11-16T19:00:00Z"
    assert ledger.verify_chain(handle.run_id)


def test_c01_tool_node_and_assessment_transparency_reconcile(c01_suspended):
    runtime, ledger, handle, path = c01_suspended
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    events = ledger.events(handle.run_id)
    calls = [event for event in events if event.type.value == "tool_call"]
    tool_results = [event for event in events if event.type.value == "tool_result"]
    assert {(event.actor.name, event.span_id) for event in calls} == {
        (event.actor.name, event.span_id) for event in tool_results
    }
    entered = [event.actor.name for event in events if event.type.value == "node_entered"]
    exited = [event.actor.name for event in events if event.type.value == "node_exited"]
    assert entered == exited
    assert entered.count("integrity") == 2
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, handle.run_id) == result.assessment.model_dump(mode="json")
