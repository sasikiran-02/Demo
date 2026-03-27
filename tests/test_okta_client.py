from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.errors import AppError
from app.security.okta_client import CachedToken, OktaTokenClient


@pytest.mark.asyncio
async def test_okta_token_retrieval_and_cache(settings) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/v1/token")
        return httpx.Response(
            200,
            json={
                "access_token": "token-123",
                "token_type": "Bearer",
                "expires_in": 120,
                "scope": settings.okta_scope,
            },
        )

    client = OktaTokenClient(settings, transport=httpx.MockTransport(handler))
    token_one, cached_one = await client.get_token()
    token_two, cached_two = await client.get_token()
    await client.close()

    assert token_one.access_token == "token-123"
    assert token_two.access_token == "token-123"
    assert cached_one is False
    assert cached_two is True
    assert calls == 1


@pytest.mark.asyncio
async def test_okta_invalid_client_maps_to_token_stage_error(settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client", "error_description": "Client authentication failed."})

    client = OktaTokenClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await client.get_token(force_refresh=True)
    await client.close()

    assert exc_info.value.stage == "token"
    assert exc_info.value.code == "invalid_client"


@pytest.mark.asyncio
async def test_okta_invalid_scope_maps_to_token_stage_error(settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_scope", "error_description": "Scope is invalid."})

    client = OktaTokenClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await client.get_token(force_refresh=True)
    await client.close()

    assert exc_info.value.stage == "token"
    assert exc_info.value.code == "invalid_scope"


def test_cached_token_refresh_window() -> None:
    token = CachedToken(
        access_token="token-123",
        token_type="Bearer",
        expires_at=datetime.now(UTC) + timedelta(seconds=20),
        scope="agent.invoke",
    )

    assert token.is_usable(datetime.now(UTC), skew_seconds=30) is False
