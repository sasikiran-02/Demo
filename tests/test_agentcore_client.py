from __future__ import annotations

import httpx
import pytest

from app.errors import AppError
from app.gateway.agentcore_client import AgentCoreGatewayClient


@pytest.mark.asyncio
async def test_agentcore_forwarding_success(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer okta-token"
        assert request.headers["x-api-key"] == "gateway-key"
        assert request.read() == b'{"message":"ping"}'
        return httpx.Response(200, json={"accepted": True})

    client = AgentCoreGatewayClient(settings, transport=httpx.MockTransport(handler))
    status_code, body = await client.invoke({"message": "ping"}, "okta-token")
    await client.close()

    assert status_code == 200
    assert body == {"accepted": True}


@pytest.mark.asyncio
async def test_agentcore_forwarding_maps_401(settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = AgentCoreGatewayClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await client.invoke({"message": "ping"}, "okta-token")
    await client.close()

    assert exc_info.value.stage == "gateway"
    assert exc_info.value.code == "gateway_unauthorized"


@pytest.mark.asyncio
async def test_agentcore_forwarding_maps_403(settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    client = AgentCoreGatewayClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await client.invoke({"message": "ping"}, "okta-token")
    await client.close()

    assert exc_info.value.stage == "gateway"
    assert exc_info.value.code == "gateway_forbidden"
