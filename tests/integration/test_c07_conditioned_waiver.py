import yaml

from conductai.app import build_runtime
from conductai.observability.replay import replay_assessment
from conductai.runtime.contracts import RunRequest
from conductai.runtime.support import leaf_paths


def _run(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c07.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


def test_c07_conditioned_waiver_leverage_substantiated(project_root, tmp_path):
    result, ledger, _ = _run(project_root, tmp_path)
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]

    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "conditioned_waiver_addon_leverage"
    assert assessment.route.depth == "L2"

    finding = assessment.findings[0]
    assert finding.category == "MC-06"
    assert finding.status == "substantiated"
    assert finding.attributable_to == "colleague"
    assert finding.severity == "high"
    assert finding.confidence == 1.0
    assert len(assessment.findings) == 1
    assert all(f.category != "MC-03" for f in assessment.findings)

    assert assessment.customer_outcome["harm_likely"] is False
    assert assessment.customer_outcome["remediation"] == [{"action": "confirm_cancellation_no_premium"}]

    assert assessment.colleague_outcome["colleague_id"] == "COL-7705"
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert set(assessment.colleague_outcome["actions"]) == {"record_colleague_finding", "assign_coaching"}

    assert assessment.control_outcome["records"] == []

    assert assessment.adjudication["panel_used"] is False
    assert assessment.adjudication["computed_confidence"] == 1.0

    memory_ops = assessment.memory_ops
    assert len(memory_ops) == 1
    assert memory_ops[0]["op"] == "supersede"
    assert memory_ops[0]["old"] == "MEM-0320"
    assert memory_ops[0]["valid_to"] == "2025-04-15"

    assert "memory_read" in types
    assert "memory_rejected" in types
    assert "memory_supersede" in types
    assert "panel_started" not in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c07_tool_node_and_assessment_transparency_reconcile(project_root, tmp_path):
    result, ledger, path = _run(project_root, tmp_path)
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
    assert set(provenance) == set(leaf_paths(assessment))

    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs

    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")


def test_c07_memory_note_verified_against_corpus_not_trusted_blindly(project_root, tmp_path):
    result, ledger, _ = _run(project_root, tmp_path)
    events = ledger.events(result.run_id)

    memory_read = next(event for event in events if event.type.value == "memory_read")
    assert memory_read.refs == ["MEM-0320"]

    memory_rejected = next(event for event in events if event.type.value == "memory_rejected")
    assert memory_rejected.payload["note_id"] == "MEM-0320"
    assert "REGZ-1026.52" in " ".join(memory_rejected.refs)

    corpus_calls = [
        event for event in events
        if event.type.value == "tool_call" and event.payload["tool"] == "retrieve_corpus_as_of"
        and event.payload["args"]["doc_id"] == "REGZ-1026.52"
    ]
    assert len(corpus_calls) == 1

    verifier_checks = {
        event.payload["check_id"]: event.payload["result"]
        for event in events if event.type.value == "verifier_check"
    }
    assert verifier_checks["colleague_statement_t02_accurate"] == "pass"
    assert verifier_checks["memory_basis_vacated"] == "pass"
    assert verifier_checks["already_entitled"] == "pass"
    assert verifier_checks["leverage_confirmed"] == "pass"

    assert all(finding.category != "MC-03" for finding in result.assessment.findings)
