from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.main import create_app


def build_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def build_jwk(private_key: rsa.RSAPrivateKey) -> dict[str, object]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "integration-key"
    jwk["alg"] = "RS256"
    return jwk


def build_signed_token(private_key: rsa.RSAPrivateKey, settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.okta_issuer,
            "aud": settings.okta_audience,
            "sub": settings.okta_client_id,
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=1),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "integration-key"},
    )


@pytest.mark.asyncio
async def test_okta_token_endpoint_returns_metadata(settings) -> None:
    def okta_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "token-123",
                "token_type": "Bearer",
                "expires_in": 120,
                "scope": settings.okta_scope,
            },
        )

    app = create_app(settings, okta_transport=httpx.MockTransport(okta_handler))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/okta/token", json={})

    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["cached"] is False


@pytest.mark.asyncio
async def test_agentcore_invoke_with_local_validation(settings) -> None:
    private_key = build_private_key()
    jwk = build_jwk(private_key)
    access_token = build_signed_token(private_key, settings)
    validated_settings = settings.model_copy(update={"enable_local_token_validation": True})

    def okta_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 120,
                "scope": validated_settings.okta_scope,
            },
        )

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json={"result": "ok"})

    app = create_app(
        validated_settings,
        okta_transport=httpx.MockTransport(okta_handler),
        jwks_transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk]})),
        gateway_transport=httpx.MockTransport(gateway_handler),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/agentcore/invoke", json={"payload": {"message": "ping"}})

    assert response.status_code == 200
    assert response.json() == {
        "gateway_status": 200,
        "gateway_body": {"result": "ok"},
        "local_validation_performed": True,
    }


@pytest.mark.asyncio
async def test_okta_token_raw_access_rejected_in_prod(settings) -> None:
    prod_settings = settings.model_copy(update={"environment": "prod", "expose_raw_access_token": True})

    def okta_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "token-123",
                "token_type": "Bearer",
                "expires_in": 120,
                "scope": prod_settings.okta_scope,
            },
        )

    app = create_app(prod_settings, okta_transport=httpx.MockTransport(okta_handler))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/okta/token", json={"access_token_only": True})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "raw_token_exposure_disabled"
