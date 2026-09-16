from datetime import UTC, datetime

import pytest
import yaml

from conductai.app import build_runtime
from conductai.observability.replay import replay_assessment
from conductai.runtime.contracts import RunRequest
from conductai.runtime.support import leaf_paths


@pytest.fixture
def c10_suspended(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c10.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path


def test_c10_suspends_for_retranscription_without_deciding_early(c10_suspended):
    runtime, ledger, handle, path = c10_suspended
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "artifact_requested" in types
    assert "wait_suspended" in types
    assert "artifact_arrived" not in types


def test_c10_resumes_and_finds_no_error_with_asr_control_gap(c10_suspended, project_root):
    _, _, handle, path = c10_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    assessment = result.assessment
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "bilingual_asr_quality"
    finding = assessment.findings[0]
    assert finding.status == "no_error"
    assert finding.attributable_to == "none"
    assert assessment.colleague_outcome["finding"] == "no_finding"
    assert assessment.customer_outcome["harm_likely"] is False
    assert assessment.control_outcome["records"][0]["system"] == "asr_model_routing"
    assert assessment.control_outcome["records"][0]["population"] == 63
    assert assessment.adjudication["panel_used"] is False
    for required in (
        "artifact_requested", "wait_suspended", "clock_advanced", "checkpoint_restored",
        "artifact_arrived", "wait_resumed", "sql_query", "fairness_check", "termination",
    ):
        assert required in types
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger.verify_chain(handle.run_id)


def test_c10_tool_node_and_assessment_transparency_reconcile(c10_suspended):
    runtime, ledger, handle, path = c10_suspended
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
    assert set(provenance) == set(leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, handle.run_id) == result.assessment.model_dump(mode="json")
