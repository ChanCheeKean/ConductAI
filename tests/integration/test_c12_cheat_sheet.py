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


_DISCARDED_IDS = {"INT-9001509", "INT-9001514"}
_AFFECTED_IDS = {
    "INT-9001501", "INT-9001502", "INT-9001503", "INT-9001504", "INT-9001505",
    "INT-9001506", "INT-9001507", "INT-9001508", "INT-9001510", "INT-9001511",
    "INT-9001512", "INT-9001513", "INT-9001515", "INT-9001516", "INT-9001517",
}
_AFFECTED_COLLEAGUES = {"COL-6630", "COL-6637", "COL-6645", "COL-6651", "COL-6658"}


@pytest.fixture
def c12_run(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/scenarios/c12.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


def test_c12_completes_with_substantiated_supervisor_material_finding(c12_run):
    result, ledger, _ = c12_run
    assessment = result.assessment
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "addon_misrepresentation_phrase_review"
    assert assessment.route.depth == "L4"
    finding = next(f for f in assessment.findings if f.category == "MC-03")
    assert finding.status == "substantiated"
    assert finding.attributable_to == "supervisor_material"
    assert finding.severity == "high"
    assert assessment.adjudication["panel_used"] is True
    assert assessment.adjudication["computed_confidence"] >= 0.75
    assert ledger.verify_chain(result.run_id)


def test_c12_fanout_events_present(c12_run):
    result, ledger, _ = c12_run
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert "fanout_started" in types
    assert "fanout_merged" in types
    assert types.count("subagent_started") == 17
    assert types.count("subagent_finished") == 17
    branch_ids = {event.branch_id for event in events if event.type.value == "subagent_started"}
    assert len(branch_ids) == 17


def test_c12_exactly_15_affected_and_2_discarded(c12_run):
    result, ledger, _ = c12_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    finding = next(f for f in assessment.findings if f.category == "MC-03")
    fact = finding.structured_evidence[0]["fact"]
    for colleague_id in _AFFECTED_COLLEAGUES:
        assert colleague_id in fact
    systemic = next(r for r in assessment.control_outcome["records"] if r["type"] == "systemic_remediation_record")
    assert systemic["population"] == 15
    assert set(systemic["colleagues"]) == _AFFECTED_COLLEAGUES
    review_updates = [event for event in events if event.type.value == "review_file_updated"]
    fanout_refs = {ref for event in review_updates for ref in event.refs}
    assert _AFFECTED_IDS <= fanout_refs
    assert _DISCARDED_IDS <= fanout_refs
    finished = [event for event in events if event.type.value == "subagent_finished"]
    by_subject = {event.payload["subject"]: event.summary for event in finished}
    assert set(by_subject) == _AFFECTED_IDS | _DISCARDED_IDS
    for affected_id in _AFFECTED_IDS:
        assert "result: misrepresentation" in by_subject[affected_id]
    for discarded_id in _DISCARDED_IDS:
        assert "result: discarded" in by_subject[discarded_id]


def test_c12_no_employment_action_against_supervisor_and_material_cited(c12_run):
    result, ledger, _ = c12_run
    assessment = result.assessment
    dumped = assessment.model_dump(mode="json")
    assert any(c["doc_id"] == "ICM-9001501" for c in assessment.citations)
    assert dumped["colleague_outcome"]["colleague_id"] != "COL-6600"
    quarantine = next(r for r in assessment.control_outcome["records"] if r["type"] == "quarantine_unapproved_material")
    assert quarantine["material_id"] == "ICM-9001501"
    text_blob = str(dumped)
    assert "COL-6600" not in dumped["colleague_outcome"].get("colleague_id", "")
    # No action list anywhere proposes discipline/termination against the supervisor.
    assert "COL-6600" not in [a for a in dumped["colleague_outcome"].get("actions", [])]


def test_c12_field_provenance_and_replay_reconcile(c12_run):
    result, ledger, path = c12_run
    events = ledger.events(result.run_id)
    calls = [event for event in events if event.type.value == "tool_call"]
    tool_results = [event for event in events if event.type.value == "tool_result"]
    assert {(event.actor.name, event.span_id) for event in calls} == {
        (event.actor.name, event.span_id) for event in tool_results
    }
    assessment = result.assessment.model_dump(mode="json")
    provenance = assessment.pop("field_provenance")
    assert set(provenance) == set(_leaf_paths(assessment))
    assessment_seq = next(event.seq for event in events if event.type.value == "assessment_recorded")
    visible_refs = {ref for event in events if event.seq < assessment_seq for ref in event.refs}
    for link in provenance.values():
        assert link["event_seqs"] and max(link["event_seqs"]) < assessment_seq
        assert link["source_refs"] and set(link["source_refs"]) <= visible_refs
    assert replay_assessment(path, result.run_id) == result.assessment.model_dump(mode="json")
