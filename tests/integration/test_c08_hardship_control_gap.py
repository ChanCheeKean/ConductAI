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


def test_c08_flex_sale_on_active_hardship_account_substantiated(c08_run):
    result, ledger, _ = c08_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "hardship_active_sale"
    assert assessment.route.depth == "L3"
    finding = assessment.findings[0]
    assert finding.category == "MC-09"
    assert finding.status == "substantiated"
    assert finding.attributable_to == "colleague"
    assert finding.severity == "high"
    assert assessment.customer_outcome["remediation"][0]["action"] == "reverse_flex_plan"
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert "assign_coaching" in assessment.colleague_outcome["actions"]
    assert "record_colleague_finding" in assessment.colleague_outcome["actions"]
    assert len(assessment.control_outcome["records"]) == 1
    assert assessment.control_outcome["records"][0]["type"] == "control_gap_record"
    assert assessment.adjudication["panel_used"] is True
    assert "graph_query" in types
    assert "panel_started" in types
    assert "panel_position" in types
    assert "adjudication" in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c08_tool_node_and_assessment_transparency_reconcile(c08_run):
    result, ledger, path = c08_run
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
