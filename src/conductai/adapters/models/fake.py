"""Deterministic model gateway for contract and integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

from conductai.config import ModelCapabilities
from conductai.runtime.contracts import ModelRequest, ModelStreamEvent


class FakeModelGateway:
    def __init__(self, events: list[ModelStreamEvent] | None = None) -> None:
        self._events = events or [ModelStreamEvent(kind="completed", payload={"text": "{}", "usage": {}})]

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            structured_output=True, tool_calling=True, streaming=True,
            reasoning_controls=True, usage_reporting=True, prompt_caching=True,
            thread_resume=True,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        for event in self._events:
            yield event
