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
def c06_suspended(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c06.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path


def test_c06_first_suspends_for_the_colleague_statement_only(c06_suspended):
    runtime, ledger, handle, path = c06_suspended
    result = runtime.result(handle.run_id)
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    requested = [event for event in events if event.type.value == "artifact_requested"]
    assert requested and requested[0].payload["kind"] == "colleague_statement"
    assert requested[0].payload["artifact_id"] == "CST-9000701"
    assert "wait_suspended" in types
    assert "colleague_statement_arrived" not in types
    assert "customer_outreach_sent" not in types
    assert "persona_reply" not in types
    assert any(event.type.value == "edge_taken" and event.payload.get("back_edge") is True for event in events)


def test_c06_first_resume_suspends_again_for_customer_outreach(c06_suspended, project_root):
    _, _, handle, path = c06_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "colleague_statement_arrived" in types
    assert "customer_outreach_sent" in types
    assert "persona_reply" not in types
    outreach = [event for event in events if event.type.value == "customer_outreach_sent"]
    assert outreach and outreach[0].payload["kind"] == "customer_reply"


def test_c06_second_resume_completes_with_expected_outcomes(c06_suspended, project_root):
    _, _, handle, path = c06_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    assessment = result.assessment
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "product_change_fee_request"
    assert assessment.route.depth == "L4"

    categories = {finding.category for finding in assessment.findings}
    assert categories == {"MC-08", "MC-11"}
    for finding in assessment.findings:
        assert finding.status == "substantiated"
        assert finding.attributable_to == "colleague"
        assert finding.severity == "high"

    remediation_actions = {item["action"] for item in assessment.customer_outcome["remediation"]}
    assert remediation_actions == {
        "reverse_product_change", "restore_rewards", "waive_annual_fee", "restore_trip_protection",
    }
    restore = next(item for item in assessment.customer_outcome["remediation"] if item["action"] == "restore_rewards")
    assert restore["amount"] == "48200"
    waive = next(item for item in assessment.customer_outcome["remediation"] if item["action"] == "waive_annual_fee")
    assert waive["amount"] == "95.00"

    assert assessment.colleague_outcome["colleague_id"] == "COL-3141"
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert set(assessment.colleague_outcome["actions"]) == {
        "record_colleague_finding", "assign_coaching", "enhanced_monitoring",
    }

    control_records = assessment.control_outcome["records"]
    assert any(record["type"] == "control_observation" for record in control_records)
    prohibited = {"incentive_clawback", "employment_action", "termination_action"}
    assert all(record["type"] not in prohibited for record in control_records)
    assert prohibited.isdisjoint(assessment.colleague_outcome["actions"])
    assert assessment.colleague_outcome["aggravating_factors"] == []

    assert assessment.adjudication["panel_used"] is True
    assert assessment.adjudication["computed_confidence"] >= 0.75

    assert len(assessment.waits) == 2
    waits_by_kind = {wait["kind"]: wait for wait in assessment.waits}
    assert set(waits_by_kind) == {"colleague_statement", "customer_reply"}
    assert waits_by_kind["colleague_statement"]["artifact_id"] == "CST-9000701"
    for wait in assessment.waits:
        assert wait["result"] == "arrived"

    assert any(event.type.value == "edge_taken" and event.payload.get("back_edge") is True for event in events)
    for required in (
        "route_decision", "skill_loaded", "transcript_assessed", "artifact_requested", "wait_suspended",
        "clock_advanced", "checkpoint_restored", "colleague_statement_arrived", "wait_resumed",
        "customer_outreach_sent", "persona_reply", "panel_started", "panel_position", "adjudication",
        "confidence_computed", "memory_write_skipped", "termination",
    ):
        assert required in types
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger.verify_chain(handle.run_id)


def test_c06_tool_node_and_assessment_transparency_reconcile(c06_suspended, project_root):
    _, _, handle, path = c06_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
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
    assert entered.count("reconcile") == 2
    assert entered.count("request_artifact") == 2

    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, handle.run_id) == result.assessment.model_dump(mode="json")
