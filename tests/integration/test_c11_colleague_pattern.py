"""C11 "One Colleague's Pattern": dynamic fan-out over 22 linked interactions via FanOutDispatcher, a one-sided
binomial test on the colleague's CardShield cancellation rate, and restraint -- 6 clean-consent interactions are
left alone and 2 recording-gap interactions are insufficient_evidence, never substantiated. Builds its own runtime
inline (C11 is intentionally not wired into conductai.app.build_runtime) so this test never touches
conductai/app.py or tests/conftest.py."""

from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

from conductai.adapters.runtime import LangGraphRuntime
from conductai.config import load_config
from conductai.data import OperationalRepository
from conductai.harness import ArtifactHarness
from conductai.observability import EventLedger
from conductai.observability.replay import replay_assessment
from conductai.runtime.c11_workflow import C11Workflow
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


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_c11_runtime(root: Path, run_database: Path) -> tuple[LangGraphRuntime, EventLedger]:
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
    tools = ToolExecutor(
        repository, ledger, harness.request_artifact,
        message_customer=harness.request_customer_message, schedule_follow_up=harness.schedule_follow_up,
    )
    workflow = WorkflowDispatcher({"C11": C11Workflow(root, config, tools, ledger)})
    runtime = LangGraphRuntime(root, config, ledger, workflow, run_database, harness)
    return runtime, ledger


@pytest.fixture
def c11_run(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c11.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = _build_c11_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, path


def test_c11_full_run_completes_and_substantiates_pattern(c11_run):
    result, ledger, _ = c11_run
    assessment = result.assessment
    assert result.status == "complete"
    assert result.termination.value == "assessment_complete"
    assert assessment.route.route_id == "addon_colleague_pattern_complaint"
    assert assessment.route.depth == "L4"
    assert assessment.adjudication["panel_used"] is True
    f1 = next(f for f in assessment.findings if f.finding_id == "F1")
    assert f1.category == "MC-02"
    assert f1.status == "substantiated"
    assert f1.attributable_to == "colleague"
    assert f1.severity == "high"
    assert f1.confidence >= 0.75
    assert assessment.colleague_outcome["finding"] == "substantiated"
    assert set(assessment.colleague_outcome["actions"]) == {
        "targeted_lookback", "record_colleague_finding", "enhanced_monitoring", "assign_coaching",
    }
    assert ledger.verify_chain(result.run_id)


def test_c11_fanout_events_cover_22_linked_interactions(c11_run):
    result, ledger, _ = c11_run
    events = ledger.events(result.run_id)
    types = [event.type.value for event in events]
    assert types.count("fanout_started") == 1
    assert types.count("fanout_merged") == 1
    fanout_started = next(event for event in events if event.type.value == "fanout_started")
    fanout_merged = next(event for event in events if event.type.value == "fanout_merged")
    assert fanout_started.payload["count"] == 22
    assert fanout_started.payload["cap"] == 24
    assert fanout_merged.payload["branches"] == 22
    assert types.count("subagent_started") == 22
    assert types.count("subagent_finished") == 22
    trigger_id = result.assessment.interaction_ids[0]
    assert trigger_id not in fanout_started.refs


def test_c11_classifies_15_substantiated_2_insufficient_6_no_error(c11_run):
    result, ledger, _ = c11_run
    assessment = result.assessment
    f1 = next(f for f in assessment.findings if f.finding_id == "F1")
    f2 = next(f for f in assessment.findings if f.finding_id == "F2")
    assert f1.status == "substantiated"
    assert f2.status == "insufficient_evidence"
    substantiated_fact = next(
        e["fact"] for e in f1.structured_evidence if e["id"] == "substantiated_interaction_ids"
    )
    assert len(substantiated_fact) == 15
    insufficient_fact = next(
        e["fact"] for e in f2.structured_evidence if e["id"] == "insufficient_evidence_interaction_ids"
    )
    assert len(insufficient_fact) == 2
    assert set(insufficient_fact) == {"INT-0421014", "INT-0421015"}
    for clean_id in ("INT-0421016", "INT-0421017", "INT-0421018", "INT-0421019", "INT-0421020", "INT-0421021"):
        assert clean_id not in substantiated_fact
        assert clean_id not in insufficient_fact
    remediation = assessment.customer_outcome["remediation"]
    reverse = next(r for r in remediation if r["action"] == "reverse_enrollment")
    assert len(reverse["enrollment_ids"]) == 17
    computation = next(event for event in ledger.events(result.run_id)
                        if event.type.value == "computation" and event.payload["helper"] == "one_sided_binomial_upper_tail")
    assert computation.payload["inputs"]["n"] == 23
    assert computation.payload["inputs"]["k"] == 14
    assert computation.payload["output"] < 0.001


def test_c11_graph_write_recorded(c11_run):
    result, ledger, _ = c11_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    graph_write_events = [e for e in events if e.type.value == "graph_write"]
    assert len(graph_write_events) == 1
    payload = graph_write_events[0].payload
    assert payload["operation"] == "edge_upsert"
    assert payload["subject"] == "ConductPattern:COL-4421"
    assert payload["status"] == "active"
    assert len(payload["evidence"]) == 15
    assert "COL-4425" not in payload["subject"]
    assert assessment.graph_writes == [{
        "operation": "edge_upsert", "subject": "ConductPattern:COL-4421",
        "status": "active", "evidence": payload["evidence"],
    }]


def test_c11_memory_consolidate_merges_three_notes(c11_run):
    result, ledger, _ = c11_run
    assessment = result.assessment
    events = ledger.events(result.run_id)
    consolidate_events = [e for e in events if e.type.value == "memory_consolidate"]
    assert len(consolidate_events) == 1
    payload = consolidate_events[0].payload
    assert set(payload["inputs"]) == {"MEM-0341", "MEM-0342", "MEM-0343"}
    assert payload["output"] == "MEM-0341-R1"
    op = next(op for op in assessment.memory_ops if op["op"] == "consolidate")
    assert set(op["inputs"]) == {"MEM-0341", "MEM-0342", "MEM-0343"}
    assert op["output"] == "MEM-0341-R1"


def test_c11_no_disciplinary_action_and_no_c11b_colleague_reference(c11_run):
    result, _ledger, _ = c11_run
    assessment = result.assessment
    forbidden = {"terminate", "termination", "suspend", "suspension", "disciplinary", "warning_letter"}
    assert forbidden.isdisjoint(set(assessment.colleague_outcome["actions"]))
    assert "COL-4425" not in assessment.model_dump_json()


def test_c11_tool_node_and_assessment_transparency_reconcile(c11_run):
    result, ledger, path = c11_run
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
