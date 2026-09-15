"""OpenAI Responses implementation of the neutral model gateway."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from conductai.config import ModelCapabilities, ModelConfig
from conductai.runtime.contracts import ModelRequest, ModelStreamEvent


class OpenAIResponsesGateway:
    """Translate the small canonical request/event surface to Responses API."""

    def __init__(self, config: ModelConfig, *, client: AsyncOpenAI | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if client is None and not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI adapter")
        self._config = config
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=config.timeout_seconds, max_retries=config.max_retries)

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._config.capabilities

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        kwargs: dict[str, Any] = {
            "model": request.requested_model,
            "input": request.messages,
            "tools": request.tools,
            "reasoning": {"effort": request.reasoning_effort, "summary": "auto"},
            "metadata": request.metadata,
            "store": False,
            "stream": True,
        }
        if request.output_schema is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "conductai_output", "strict": True,
                                          "schema": request.output_schema}}
        stream = await self._client.responses.create(**kwargs)
        async for event in stream:
            event_type = getattr(event, "type", type(event).__name__)
            if event_type == "response.output_text.delta":
                yield ModelStreamEvent(kind="text_delta", payload={"delta": event.delta})
            elif event_type == "response.completed":
                response = event.response
                usage = response.usage.model_dump() if response.usage else {}
                yield ModelStreamEvent(
                    kind="completed",
                    payload={"response_id": response.id, "model": response.model,
                             "output_text": response.output_text, "usage": usage,
                             "status": response.status},
                )
            elif event_type == "response.failed":
                yield ModelStreamEvent(kind="failed", payload={"error": "provider_response_failed"})
            else:
                yield ModelStreamEvent(kind="provider_event", payload={"type": event_type})
