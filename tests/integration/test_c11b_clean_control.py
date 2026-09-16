import yaml

from conductai.app import build_runtime
from conductai.observability.replay import replay_assessment
from conductai.runtime.contracts import RunRequest
from conductai.runtime.support import leaf_paths


def _run(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c11b.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


def test_c11b_no_error_and_rejects_teammate_pattern(project_root, tmp_path):
    result, ledger, path = _run(project_root, tmp_path)
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    finding = result.assessment.findings[0]
    assert finding.status == "no_error"
    assert result.assessment.colleague_outcome["finding"] == "no_finding"
    assert result.assessment.colleague_outcome["actions"] == []
    assert result.assessment.adjudication["panel_used"] is False
    assert "memory_read" in types
    assert "memory_rejected" in types
    memory_rejected = next(event for event in events if event.type.value == "memory_rejected")
    assert memory_rejected.payload["note_id"] == "MEM-0341"
    assert "COL-4425" in memory_rejected.payload["reason"]
    assert ledger.verify_chain(result.run_id)


def test_c11b_own_cancellation_rate_computed_not_imported(project_root, tmp_path):
    result, ledger, path = _run(project_root, tmp_path)
    events = ledger.events(result.run_id)
    finding_updated = next(event for event in events if event.type.value == "finding_updated")
    assert 0 <= finding_updated.payload["own_cancellation_rate"] <= 0.15
    assert finding_updated.payload["own_enrollment_count"] == 19


def test_c11b_transparency_reconciles(project_root, tmp_path):
    result, ledger, path = _run(project_root, tmp_path)
    events = ledger.events(result.run_id)
    calls = [event for event in events if event.type.value == "tool_call"]
    tool_results = [event for event in events if event.type.value == "tool_result"]
    assert {(event.actor.name, event.span_id) for event in calls} == {
        (event.actor.name, event.span_id) for event in tool_results
    }
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")
