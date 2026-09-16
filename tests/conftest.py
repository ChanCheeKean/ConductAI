from pathlib import Path

import pytest
import yaml

from conductai.app import build_runtime
from conductai.runtime.contracts import RunRequest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def c03_run(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c03.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


@pytest.fixture
def c01_suspended(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c01.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path


def _run_scenario(project_root: Path, tmp_path: Path, scenario: str):
    raw = yaml.safe_load((project_root / f"config/scenarios/{scenario}.yaml").read_text())
    runtime, ledger = build_runtime(project_root, tmp_path / "run.sqlite")
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime.result(handle.run_id), ledger, tmp_path / "run.sqlite"


@pytest.fixture
def c07b_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c07b")


@pytest.fixture
def c19_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c19")


@pytest.fixture
def c05_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c05")


@pytest.fixture
def c04_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c04")


@pytest.fixture
def c02_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c02")


@pytest.fixture
def c02b_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c02b")


@pytest.fixture
def c08_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c08")


@pytest.fixture
def c16_run(project_root: Path, tmp_path: Path):
    return _run_scenario(project_root, tmp_path, "c16")


@pytest.fixture
def c15_suspended(project_root: Path, tmp_path: Path):
    raw = yaml.safe_load((project_root / "config/scenarios/c15.yaml").read_text())
    path = tmp_path / "run.sqlite"
    runtime, ledger = build_runtime(project_root, path)
    request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
    handle = runtime.start(request)
    list(runtime.run_or_stream(handle))
    return runtime, ledger, handle, path
