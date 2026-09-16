import yaml
import pytest

from conductai.app import build_runtime
from conductai.observability.replay import replay_assessment
from conductai.runtime.contracts import RunRequest


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


@pytest.fixture
def c18_suspended_first(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c18.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path


def test_c18_suspends_for_audio_recovery_first(c18_suspended_first):
    runtime, ledger, handle, path = c18_suspended_first
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "artifact_requested" in types
    assert "wait_suspended" in types
    assert "artifact_arrived" not in types
    assert "customer_outreach_sent" not in types
    assert "persona_reply" not in types
    requested = next(
        event for event in ledger.events(handle.run_id) if event.type.value == "artifact_requested"
    )
    assert requested.payload["artifact_id"] == "AUD-9002101"
    assert requested.payload["kind"] == "audio_recovery"


def test_c18_resumes_once_and_suspends_again_for_customer_outreach(c18_suspended_first, project_root):
    _, _, handle, path = c18_suspended_first
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "artifact_arrived" in types
    assert "wait_resumed" in types
    assert "customer_outreach_sent" in types
    assert "persona_reply" not in types
    assert types.count("wait_suspended") == 2
    entered = [event.actor.name for event in ledger.events(handle.run_id) if event.type.value == "node_entered"]
    assert entered.count("integrity") == 2


def test_c18_resumes_twice_and_reaches_insufficient_evidence(c18_suspended_first, project_root):
    _, _, handle, path = c18_suspended_first
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    runtime2, ledger2 = build_runtime(project_root, path)
    list(runtime2.resume(handle.run_id))
    result = runtime2.result(handle.run_id)
    assessment = result.assessment
    events = ledger2.events(handle.run_id)
    types = [event.type.value for event in events]

    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "recording_gap_addon_review"

    finding = assessment.findings[0]
    assert finding.category == "MC-02"
    assert finding.status == "insufficient_evidence"
    assert finding.attributable_to == "none"
    assert finding.confidence < 0.75

    assert assessment.colleague_outcome["finding"] == "no_adverse_finding"
    assert assessment.colleague_outcome["actions"] == []
    assert assessment.customer_outcome["harm_likely"] is True
    assert assessment.customer_outcome["remediation"] == [{"action": "reverse_enrollment"}]
    control_record = assessment.control_outcome["records"][0]
    assert control_record["incident_id"] == "INC-9002101"
    assert control_record["population"] == 23
    assert control_record["sales_during_gap"] == 4

    assert assessment.adjudication["panel_used"] is True
    assert assessment.adjudication["computed_confidence"] < 0.75
    assert assessment.adjudication["conservative_default_applied"] is True

    for required in (
        "artifact_requested", "wait_suspended", "clock_advanced", "checkpoint_restored",
        "artifact_arrived", "wait_resumed", "customer_outreach_sent", "persona_reply",
        "panel_started", "panel_position", "adjudication", "confidence_computed",
        "conservative_default_applied", "termination",
    ):
        assert required in types
    assert types.count("panel_position") == 2
    assert types.count("wait_suspended") == 2
    assert types.count("artifact_arrived") == 1
    assert types.count("persona_reply") == 1

    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger2.verify_chain(handle.run_id)

    assessment_dump = assessment.model_dump(mode="json")
    provenance = assessment_dump.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment_dump))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs

    assert replay_assessment(path, handle.run_id) == result.assessment.model_dump(mode="json")
