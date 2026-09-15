import asyncio

import pytest

from conductai.adapters.models import FakeModelGateway, OpenAIResponsesGateway
from conductai.config import load_config
from conductai.runtime.contracts import ModelRequest


def test_fake_gateway_contract(project_root):
    gateway = FakeModelGateway()
    request = ModelRequest(messages=[{"role": "user", "content": "test"}], requested_model="fake",
                           idempotency_key="test-1")

    async def collect():
        return [event async for event in gateway.stream(request)]

    assert asyncio.run(collect())[-1].kind == "completed"
    assert gateway.capabilities.structured_output


def test_openai_gateway_requires_environment_credential(project_root, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_config(project_root).models.models["default"]
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIResponsesGateway(config)
