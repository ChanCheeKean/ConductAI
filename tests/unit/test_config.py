from pydantic import ValidationError
import pytest

from conductai.config import load_config


def test_config_is_valid_immutable_and_secret_free(project_root, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-must-not-leak")
    config = load_config(project_root)
    assert config.models.models["default"].model == "gpt-5.6-luna"
    assert "sk-test" not in str(config.secret_free_snapshot())
    with pytest.raises(ValidationError):
        config.snapshot_hash = "changed"


def test_model_override_is_configuration_only(project_root, monkeypatch):
    monkeypatch.setenv("CONDUCTAI_MODEL", "fake-model")
    assert load_config(project_root).models.models["default"].model == "fake-model"
