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


def test_c16_post_call_enrollment_substantiated_with_lookback_opened(c16_run):
    result, ledger, _ = c16_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "post_call_addon_review"
    finding = assessment.findings[0]
    assert finding.category == "MC-02"
    assert finding.status == "substantiated"
    assert finding.attributable_to == "colleague"
    assert finding.severity == "high"
    assert assessment.customer_outcome["remediation"] == [
        {"action": "reverse_enrollment"}, {"action": "refund_fee", "amount": "14.99"},
    ]
    assert "targeted_lookback" in assessment.colleague_outcome["actions"]
    assert "enhanced_monitoring" in assessment.colleague_outcome["actions"]
    assert assessment.adjudication["panel_used"] is False
    assert "sql_query" in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c16_tool_node_and_assessment_transparency_reconcile(c16_run):
    result, ledger, path = c16_run
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
