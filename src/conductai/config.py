"""Validated, immutable configuration resolution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from conductai.domain.models import Budget


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelCapabilities(FrozenModel):
    structured_output: bool
    tool_calling: bool
    streaming: bool
    reasoning_controls: bool
    usage_reporting: bool
    prompt_caching: bool
    thread_resume: bool


class ModelConfig(FrozenModel):
    provider: str
    model: str
    adapter: str
    reasoning_effort: str
    timeout_seconds: int = Field(gt=0)
    max_retries: int = Field(ge=0, le=5)
    capabilities: ModelCapabilities


class ModelsConfig(FrozenModel):
    schema_version: Literal[1]
    default_role: str
    models: dict[str, ModelConfig]

    @model_validator(mode="after")
    def default_exists(self) -> "ModelsConfig":
        if self.default_role not in self.models:
            raise ValueError("default_role does not resolve to a model")
        return self


class RouteOutput(FrozenModel):
    track: Literal["sales", "servicing", "mixed", "portfolio"]
    depth: Literal["L1", "L2", "L3", "L4", "Q01"]
    path: str
    budget: Budget
    roles: tuple[str, ...]
    skills: tuple[str, ...]
    rationale: str
    action_profile: str | None = None


class RouteRule(FrozenModel):
    id: str
    priority: int
    match: dict[str, Any]
    output: RouteOutput


class RouteDefaults(FrozenModel):
    classifier_threshold: float = Field(ge=0, le=1)
    fallback_route: str


class RoutesConfig(FrozenModel):
    schema_version: Literal[1]
    defaults: RouteDefaults
    routes: tuple[RouteRule, ...]

    @model_validator(mode="after")
    def registry_is_valid(self) -> "RoutesConfig":
        ids = [route.id for route in self.routes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate route id")
        if self.defaults.fallback_route not in ids:
            raise ValueError("fallback route does not exist")
        if list(self.routes) != sorted(self.routes, key=lambda route: route.priority):
            raise ValueError("routes must be ordered by ascending priority")
        return self


class ResolvedConfig(FrozenModel):
    models: ModelsConfig
    routes: RoutesConfig
    snapshot_hash: str

    def secret_free_snapshot(self) -> dict[str, Any]:
        return {"models": self.models.model_dump(), "routes": self.routes.model_dump(), "snapshot_hash": self.snapshot_hash}


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def load_config(root: Path) -> ResolvedConfig:
    """Resolve files and safe environment overrides once at startup."""
    models_raw = _read_yaml(root / "config" / "models.yaml")
    routes_raw = _read_yaml(root / "config" / "routes.yaml")
    role = models_raw["default_role"]
    selected = models_raw["models"][role]
    if model_override := os.getenv("CONDUCTAI_MODEL"):
        selected["model"] = model_override
    if provider_override := os.getenv("CONDUCTAI_PROVIDER"):
        selected["provider"] = provider_override
    models = ModelsConfig.model_validate(models_raw)
    routes = RoutesConfig.model_validate(routes_raw)
    material = {"models": models.model_dump(), "routes": routes.model_dump()}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ResolvedConfig(models=models, routes=routes, snapshot_hash=f"sha256:{digest}")
