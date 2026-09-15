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


def test_c05_reconciles_stated_versus_submitted_rate(c05_run):
    result, ledger, _ = c05_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "balance_transfer_disclosure"
    assert assessment.route.depth == "L3"
    statuses = {finding.category: finding.status for finding in assessment.findings}
    assert statuses == {"MC-03": "substantiated", "MC-04": "substantiated"}
    assert all(finding.attributable_to == "colleague" for finding in assessment.findings)
    remediation = next(r for r in assessment.customer_outcome["remediation"] if r["action"] == "refund_fee")
    assert remediation["amount"] == "124.00"
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert "assign_coaching" in assessment.colleague_outcome["actions"]
    computation = next(event for event in events if event.type.value == "computation")
    assert computation.payload["output"]["fee_at_submitted_rate"] == "310.00"
    assert computation.payload["output"]["fee_at_stated_rate"] == "186.00"
    assert computation.payload["output"]["remediation"] == "124.00"
    assert "panel_started" not in types
    assert "memory_write_skipped" in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c05_distinguishes_the_precedent_instead_of_following_it(c05_run):
    result, ledger, _ = c05_run
    events = ledger.events(result.run_id)
    checks = {
        event.payload["check_id"]: event.payload["result"]
        for event in events if event.type.value == "verifier_check"
    }
    assert checks["precedent_distinguished"] == "pass"
    citation_docs = {citation["doc_id"] for citation in result.assessment.citations}
    assert "PRE-0022" in citation_docs


def test_c05_tool_node_and_assessment_transparency_reconcile(c05_run):
    result, ledger, path = c05_run
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
