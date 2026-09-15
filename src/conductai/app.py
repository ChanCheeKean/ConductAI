"""Composition root for local ConductAI runs."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from conductai.adapters.runtime import LangGraphRuntime
from conductai.adapters.runtime.deepagents_lead import DeepAgentsLeadAdapter
from conductai.config import load_config
from conductai.data import OperationalRepository
from conductai.harness import ArtifactHarness
from conductai.observability import EventLedger
from conductai.runtime.c01_workflow import C01Workflow
from conductai.runtime.c03_workflow import C03Workflow
from conductai.runtime.workflow import WorkflowDispatcher
from conductai.tools import ToolExecutor


def build_runtime(root: Path, run_database: Path) -> tuple[LangGraphRuntime, EventLedger]:
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
    tools = ToolExecutor(repository, ledger, harness.request_artifact)
    lead = DeepAgentsLeadAdapter(ledger)
    workflow = WorkflowDispatcher(
        C01Workflow(root, config, tools, ledger, lead),
        C03Workflow(root, config, tools, ledger),
    )
    runtime = LangGraphRuntime(root, config, ledger, workflow, run_database, harness)
    return runtime, ledger
