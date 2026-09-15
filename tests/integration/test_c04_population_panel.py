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


def test_c04_reroutes_from_colleague_to_systemic_control_gap(c04_run):
    result, ledger, _ = c04_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "cli_script_root_cause"
    assert assessment.route.depth == "L4"
    finding = assessment.findings[0]
    assert finding.category == "MC-05"
    assert finding.status == "control_gap"
    assert finding.attributable_to == "script"
    assert assessment.colleague_outcome["finding"] == "no_finding"
    remediation = assessment.customer_outcome["remediation"]
    assert remediation == [{"action": "correction_letter"}]
    systemic = next(r for r in assessment.control_outcome["records"] if r["type"] == "systemic_remediation_record")
    assert systemic["population"] == 41
    assert set(systemic["colleagues"]) == {"COL-4409", "COL-4430"}
    supersede = next(op for op in assessment.memory_ops if op["op"] == "supersede")
    assert supersede["old"] == "MEM-0310"
    assert "memory_rejected" in types
    assert "panel_started" in types
    assert types.count("panel_position") == 2
    assert "adjudication" in types
    assert any(
        event.type.value == "edge_taken" and event.payload.get("back_edge") is True
        for event in events
    )
    computation = next(event for event in events if event.type.value == "computation" and event.payload["helper"] == "population_count")
    assert computation.payload["output"] == 41
    assert computation.payload["inputs"]["excluded_correct_warning"] == 6
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c04_tool_node_and_assessment_transparency_reconcile(c04_run):
    result, ledger, path = c04_run
    events = ledger.events(result.run_id)
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
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")
