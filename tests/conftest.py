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
