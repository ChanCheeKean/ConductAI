from pathlib import Path

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
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def c13_run(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c13.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


def test_c13_uncoded_complaint_substantiates_mc10_and_mc11(c13_run):
    result, ledger, _ = c13_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "uncoded_complaint_handling"
    assert len(assessment.findings) == 2
    categories = {finding.category for finding in assessment.findings}
    assert categories == {"MC-10", "MC-11"}
    for finding in assessment.findings:
        assert finding.status == "substantiated"
        assert finding.attributable_to == "colleague"
        assert finding.severity == "medium"
    assert assessment.customer_outcome["remediation"] == [
        {"action": "log_complaint", "received_at": "2026-11-03T17:00:00Z"},
    ]
    assert not any(action.get("action") == "refund_fee" for action in assessment.customer_outcome["remediation"])
    assert assessment.colleague_outcome["colleague_id"] == "COL-3177"
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert assessment.colleague_outcome["actions"] == ["record_colleague_finding", "assign_coaching"]
    assert assessment.control_outcome["records"] == []
    assert assessment.adjudication["panel_used"] is False
    assert assessment.waits == []
    assert "request_artifact" not in types
    assert "wait_suspended" not in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c13_tool_node_and_assessment_transparency_reconcile(c13_run):
    result, ledger, path = c13_run
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


def test_c13_ledger_chain_and_replay_are_deterministic(c13_run):
    result, ledger, path = c13_run
    assert ledger.verify_chain(result.run_id)
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")
