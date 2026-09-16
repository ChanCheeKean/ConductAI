from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

from conductai.adapters.runtime import LangGraphRuntime
from conductai.config import load_config
from conductai.data import OperationalRepository
from conductai.harness import ArtifactHarness
from conductai.memory import GraphRepository
from conductai.observability import EventLedger
from conductai.observability.replay import replay_assessment
from conductai.runtime.c09_workflow import C09Workflow
from conductai.runtime.contracts import RunRequest
from conductai.runtime.workflow import WorkflowDispatcher
from conductai.tools import ToolExecutor


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


def _build_c09_runtime(root: Path, run_database: Path) -> tuple[LangGraphRuntime, EventLedger]:
    """Builds a runtime wired only with C09Workflow, without touching app.build_runtime or conftest.py."""
    config = load_config(root)
    runtime_snapshot = {
        "snapshot_hash": config.snapshot_hash,
        "provider": config.models.models[config.models.default_role].provider,
        "model": config.models.models[config.models.default_role].model,
        "model_adapter": config.models.models[config.models.default_role].adapter,
        "agent_runtime": "langgraph",
        "versions": {
            "conductai": version("conductai"),
            "langgraph": version("langgraph"),
            "deepagents": version("deepagents"),
            "openai": version("openai"),
        },
    }
    ledger = EventLedger(run_database, runtime_snapshot)
    harness = ArtifactHarness(root / "data" / "generated", run_database, ledger)
    repository = OperationalRepository(root / "data" / "generated" / "conduct.sqlite", ledger)
    graph = GraphRepository(root / "data" / "generated" / "graph", ledger)
    tools = ToolExecutor(
        repository, ledger, harness.request_artifact, graph=graph,
        message_customer=harness.request_customer_message, schedule_follow_up=harness.schedule_follow_up,
    )
    workflow = WorkflowDispatcher({"C09": C09Workflow(root, config, tools, ledger)})
    runtime = LangGraphRuntime(root, config, ledger, workflow, run_database, harness)
    return runtime, ledger


@pytest.fixture
def c09_run(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c09.yaml").read_text())
    run_database = tmp_path / "run.sqlite"
    runtime, ledger = _build_c09_runtime(project_root, run_database)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, run_database


def test_c09_scra_misinformation_substantiated(c09_run):
    result, ledger, _ = c09_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "scra_rights_referral"
    assert assessment.route.depth == "L3"
    assert len(assessment.findings) == 1
    finding = assessment.findings[0]
    assert finding.category == "MC-10"
    assert finding.status == "substantiated"
    assert finding.attributable_to == "colleague"
    assert finding.severity == "high"
    remediation_actions = {row["action"] for row in assessment.customer_outcome["remediation"]}
    assert remediation_actions == {"open_scra_review", "correction_letter"}
    assert assessment.customer_outcome["harm_likely"] is True
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert "assign_coaching" in assessment.colleague_outcome["actions"]
    assert "record_colleague_finding" in assessment.colleague_outcome["actions"]
    assert assessment.control_outcome["records"] == []
    assert assessment.adjudication["panel_used"] is True
    assert "rights misinformation" in assessment.adjudication["panel_reason"]
    assert assessment.memory_ops == [{"op": "skip", "reason": "case-local finding; no generalizable pattern",
                                       "source_refs": ["INT-9001101"]}]
    assert "panel_started" in types
    assert types.count("panel_position") == 2
    assert "adjudication" in types
    assert "confidence_computed" in types
    assert "retrieval_decision" in types
    assert events[-1].type.value == "termination"
    assert ledger.verify_chain(result.run_id)


def test_c09_precedent_rejected_not_followed(c09_run):
    result, ledger, _ = c09_run
    events = ledger.events(result.run_id)
    decision = next(event for event in events if event.type.value == "retrieval_decision")
    assert decision.payload["used"] == []
    assert decision.payload["discarded"][0]["id"] == "PRE-0031"
    checks = {event.payload["check_id"]: event.payload["result"]
              for event in events if event.type.value == "verifier_check"}
    assert checks["precedent_rejected_against_primary_text"] == "pass"
    citations = {row["doc_id"] for row in result.assessment.citations}
    assert "PRE-0031" in citations
    assert "CLB-SOP-SCRA-001@v3" in citations


def test_c09_tool_node_and_assessment_transparency_reconcile(c09_run):
    result, ledger, path = c09_run
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
