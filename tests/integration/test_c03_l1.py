import json
import sqlite3

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


def test_c03_completes_cheaply_with_full_trajectory(c03_run):
    result, ledger, _ = c03_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "cli_soft_pull_clean"
    assert assessment.route.depth == "L1"
    assert assessment.findings[0].status == "no_error"
    assert assessment.customer_outcome["remediation"] == [{"action": "none"}]
    assert assessment.colleague_outcome["finding"] == "no_finding"
    assert assessment.control_outcome["records"] == []
    assert len([event for event in events if event.type.value == "tool_call"]) == 5
    assert "llm_call" not in types and "agent_started" not in types
    assert "skill_loaded" in types
    assert "memory_write_skipped" in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_every_tool_and_node_has_complete_instrumentation(c03_run):
    result, ledger, _ = c03_run
    events = ledger.events(result.run_id)
    calls = [event for event in events if event.type.value == "tool_call"]
    results = [event for event in events if event.type.value == "tool_result"]
    assert {(event.actor.name, event.span_id) for event in calls} == {(event.actor.name, event.span_id) for event in results}
    entered = [event.actor.name for event in events if event.type.value == "node_entered"]
    exited = [event.actor.name for event in events if event.type.value == "node_exited"]
    assert entered == exited
    assert len(entered) == 11
    assert len([event for event in events if event.type.value == "edge_taken"]) == 11
    assert len([event for event in events if event.type.value == "checkpoint_saved"]) == 11


def test_assessment_provenance_is_complete_and_replayable(c03_run):
    result, ledger, path = c03_run
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in ledger.events(result.run_id) if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in ledger.events(result.run_id) if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")


def test_langgraph_persisted_checkpoints(c03_run):
    result, _, path = c03_run
    with sqlite3.connect(path) as conn:
        checkpoint_count = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (result.run_id,)).fetchone()[0]
    assert checkpoint_count >= 11
