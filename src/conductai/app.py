"""Composition root for local ConductAI runs."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from conductai.adapters.runtime import LangGraphRuntime
from conductai.adapters.runtime.deepagents_lead import DeepAgentsLeadAdapter
from conductai.config import load_config
from conductai.data import OperationalRepository
from conductai.harness import ArtifactHarness
from conductai.memory import GraphRepository
from conductai.observability import EventLedger
from conductai.runtime.c01_workflow import C01Workflow
from conductai.runtime.c02_workflow import C02Workflow
from conductai.runtime.c02b_workflow import C02bWorkflow
from conductai.runtime.c03_workflow import C03Workflow
from conductai.runtime.c04_workflow import C04Workflow
from conductai.runtime.c05_workflow import C05Workflow
from conductai.runtime.c06_workflow import C06Workflow
from conductai.runtime.c07_workflow import C07Workflow
from conductai.runtime.c07b_workflow import C07bWorkflow
from conductai.runtime.c08_workflow import C08Workflow
from conductai.runtime.c09_workflow import C09Workflow
from conductai.runtime.c10_workflow import C10Workflow
from conductai.runtime.c11_workflow import C11Workflow
from conductai.runtime.c11b_workflow import C11bWorkflow
from conductai.runtime.c12_workflow import C12Workflow
from conductai.runtime.c13_workflow import C13Workflow
from conductai.runtime.c14_workflow import C14Workflow
from conductai.runtime.c15_workflow import C15Workflow
from conductai.runtime.c16_workflow import C16Workflow
from conductai.runtime.c17_workflow import C17Workflow
from conductai.runtime.c18_workflow import C18Workflow
from conductai.runtime.c19_workflow import C19Workflow
from conductai.runtime.c20_workflow import C20Workflow
from conductai.runtime.q01_selector import Q01Selector
from conductai.runtime.workflow import WorkflowDispatcher
from conductai.tools import ToolExecutor


def _runtime_snapshot(config) -> dict:
    return {
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


def build_runtime(root: Path, run_database: Path) -> tuple[LangGraphRuntime, EventLedger]:
    config = load_config(root)
    ledger = EventLedger(run_database, _runtime_snapshot(config))
    harness = ArtifactHarness(root / "data" / "generated", run_database, ledger)
    repository = OperationalRepository(root / "data" / "generated" / "conduct.sqlite", ledger)
    graph = GraphRepository(root / "data" / "generated" / "graph", ledger)
    tools = ToolExecutor(
        repository, ledger, harness.request_artifact, graph=graph,
        message_customer=harness.request_customer_message, schedule_follow_up=harness.schedule_follow_up,
    )
    lead = DeepAgentsLeadAdapter(ledger)
    workflow = WorkflowDispatcher({
        "C01": C01Workflow(root, config, tools, ledger, lead),
        "C02": C02Workflow(root, config, tools, ledger),
        "C02b": C02bWorkflow(root, config, tools, ledger),
        "C03": C03Workflow(root, config, tools, ledger),
        "C04": C04Workflow(root, config, tools, ledger),
        "C05": C05Workflow(root, config, tools, ledger),
        "C06": C06Workflow(root, config, tools, ledger),
        "C07": C07Workflow(root, config, tools, ledger),
        "C07b": C07bWorkflow(root, config, tools, ledger),
        "C08": C08Workflow(root, config, tools, ledger),
        "C09": C09Workflow(root, config, tools, ledger),
        "C10": C10Workflow(root, config, tools, ledger),
        "C11": C11Workflow(root, config, tools, ledger),
        "C11b": C11bWorkflow(root, config, tools, ledger),
        "C12": C12Workflow(root, config, tools, ledger),
        "C13": C13Workflow(root, config, tools, ledger),
        "C14": C14Workflow(root, config, tools, ledger),
        "C15": C15Workflow(root, config, tools, ledger),
        "C16": C16Workflow(root, config, tools, ledger),
        "C17": C17Workflow(root, config, tools, ledger),
        "C18": C18Workflow(root, config, tools, ledger),
        "C19": C19Workflow(root, config, tools, ledger),
        "C20": C20Workflow(root, config, tools, ledger),
    })
    runtime = LangGraphRuntime(root, config, ledger, workflow, run_database, harness)
    return runtime, ledger


def build_selector(root: Path, run_database: Path) -> tuple[Q01Selector, EventLedger]:
    """Composition root for the standalone Q01 weekly portfolio selection (not a review run)."""
    config = load_config(root)
    ledger = EventLedger(run_database, _runtime_snapshot(config))
    repository = OperationalRepository(root / "data" / "generated" / "conduct.sqlite", ledger)
    return Q01Selector(root, config, repository, ledger), ledger
