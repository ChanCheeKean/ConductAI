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


def test_c07b_clock_skew_clears_the_waiver_before_the_pitch(c07b_run):
    result, ledger, _ = c07b_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "conditioned_servicing_event_time"
    assert assessment.route.depth == "L2"
    assert assessment.findings[0].status == "no_error"
    assert assessment.findings[0].evidence_spans[0]["quote"] == "Yes, add it."
    assert assessment.customer_outcome["remediation"] == [{"action": "none"}]
    assert assessment.colleague_outcome["finding"] == "no_finding"
    assert assessment.control_outcome["records"] == []
    computation = next(event for event in events if event.type.value == "computation")
    assert computation.payload["output"] == "2026-11-10T21:17:53Z"
    reconciled = next(event for event in events if event.type.value == "finding_updated")
    assert reconciled.payload["seconds_before_mention"] == 19
    assert reconciled.payload["seconds_before_pitch"] == 47
    assert "memory_write_skipped" in types
    assert "panel_started" not in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c07b_tool_node_and_assessment_transparency_reconcile(c07b_run):
    result, ledger, path = c07b_run
    events = ledger.events(result.run_id)
    calls = [event for event in events if event.type.value == "tool_call"]
    tool_results = [event for event in events if event.type.value == "tool_result"]
    assert {(event.actor.name, event.span_id) for event in calls} == {
        (event.actor.name, event.span_id) for event in tool_results
    }
    entered = [event.actor.name for event in events if event.type.value == "node_entered"]
    exited = [event.actor.name for event in events if event.type.value == "node_exited"]
    assert entered == exited
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")


def test_c07b_persisted_checkpoints(c07b_run):
    result, _, path = c07b_run
    with sqlite3.connect(path) as conn:
        checkpoint_count = conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (result.run_id,)
        ).fetchone()[0]
    assert checkpoint_count >= 1
