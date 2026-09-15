"""Narrow replaceable model and agent-runtime protocols."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from conductai.config import ModelCapabilities
from conductai.domain.models import RunResult


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelRequest(RuntimeModel):
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    requested_model: str
    reasoning_effort: str = "medium"
    metadata: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str


class ModelStreamEvent(RuntimeModel):
    kind: str
    payload: dict[str, Any]


class ModelGateway(Protocol):
    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]: ...


class RunRequest(RuntimeModel):
    scenario_id: str
    review_id: str
    interaction_ids: list[str]
    trigger: dict[str, Any]
    virtual_now: str


class RunHandle(RuntimeModel):
    run_id: str
    review_id: str


class RuntimeEvent(RuntimeModel):
    type: str
    payload: dict[str, Any]


class AgentRuntime(Protocol):
    def start(self, request: RunRequest) -> RunHandle: ...
    def run_or_stream(self, handle: RunHandle) -> Iterator[RuntimeEvent]: ...
    def result(self, run_id: str) -> RunResult: ...
    def cancel(self, run_id: str, reason: str) -> None: ...
