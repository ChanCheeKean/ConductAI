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


def test_c15_suspends_for_customer_outreach_without_deciding_early(c15_suspended):
    runtime, ledger, handle, path = c15_suspended
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "customer_outreach_sent" in types
    assert "wait_suspended" in types
    assert "persona_reply" not in types


def test_c15_resumes_and_finds_a_control_gap_not_colleague_fault(c15_suspended, project_root):
    _, _, handle, path = c15_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    assessment = result.assessment
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "preference_suppression_incident"
    finding = assessment.findings[0]
    assert finding.category == "MC-09"
    assert finding.status == "control_gap"
    assert finding.attributable_to == "system"
    assert assessment.colleague_outcome["finding"] == "no_finding"
    assert assessment.colleague_outcome["actions"] == []
    assert assessment.customer_outcome["remediation"] == [{"action": "suppress_solicitation"}]
    assert assessment.customer_outcome["customer_choice"] == "keep_transfer"
    assert assessment.control_outcome["records"][0]["population"] == 9
    assert assessment.adjudication["panel_used"] is False
    assert any(event.type.value == "edge_taken" and event.payload.get("back_edge") is True for event in events)
    for required in (
        "customer_outreach_sent", "wait_suspended", "clock_advanced", "checkpoint_restored",
        "persona_reply", "wait_resumed", "sql_query", "termination",
    ):
        assert required in types
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger.verify_chain(handle.run_id)


def test_c15_tool_node_and_assessment_transparency_reconcile(c15_suspended):
    runtime, ledger, handle, path = c15_suspended
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
