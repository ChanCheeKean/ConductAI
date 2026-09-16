import pytest
import yaml

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
def c17_suspended(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c17.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path


def test_c17_suspends_for_customer_outreach_without_deciding_early(c17_suspended):
    runtime, ledger, handle, path = c17_suspended
    result = runtime.result(handle.run_id)
    types = [event.type.value for event in ledger.events(handle.run_id)]
    assert result.status == "suspended"
    assert result.termination.value == "waiting_external"
    assert result.assessment is None
    assert "customer_outreach_sent" in types
    assert "wait_suspended" in types
    assert "persona_reply" not in types


def test_c17_resumes_and_finds_mc05_and_mc06_substantiated(c17_suspended, project_root):
    _, _, handle, path = c17_suspended
    runtime, ledger = build_runtime(project_root, path)
    list(runtime.resume(handle.run_id))
    result = runtime.result(handle.run_id)
    assessment = result.assessment
    events = ledger.events(handle.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "retention_cancellation_review"

    findings = {finding.category: finding for finding in assessment.findings}
    assert set(findings) == {"MC-05", "MC-06"}
    for finding in findings.values():
        assert finding.status == "substantiated"
        assert finding.attributable_to == "colleague"
        assert finding.severity == "medium"

    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert assessment.colleague_outcome["actions"] == ["record_colleague_finding", "assign_coaching"]

    remediation = assessment.customer_outcome["remediation"]
    assert {"action": "honor_cancellation_request"} in remediation
    assert {"action": "refund_annual_fee", "amount": "450.00"} in remediation
    # the $200 retention credit was applied in good faith and is not clawed back
    assert not any(item.get("action") == "claw_back_retention_credit" for item in remediation)

    assert assessment.adjudication["panel_used"] is False
    assert assessment.control_outcome["records"] == []

    for required in (
        "customer_outreach_sent", "wait_suspended", "clock_advanced", "checkpoint_restored",
        "persona_reply", "wait_resumed", "sql_query", "termination", "retrieval_decision", "computation",
    ):
        assert required in types
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger.verify_chain(handle.run_id)


def test_c17_tool_node_and_assessment_transparency_reconcile(c17_suspended):
    runtime, ledger, handle, path = c17_suspended
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
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, handle.run_id) == result.assessment.model_dump(mode="json")
