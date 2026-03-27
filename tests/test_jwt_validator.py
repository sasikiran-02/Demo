from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.errors import AppError
from app.security.jwt_validator import JWTValidator


def build_signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-key"
    jwk["alg"] = "RS256"
    return private_key, jwk


def build_token(private_key: rsa.RSAPrivateKey, settings, *, audience: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.okta_issuer,
            "aud": audience,
            "sub": settings.okta_client_id,
            "exp": now + expires_delta,
            "nbf": now - timedelta(seconds=1),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


@pytest.mark.asyncio
async def test_jwt_validation_success(settings) -> None:
    private_key, jwk = build_signing_material()
    token = build_token(private_key, settings, audience=settings.okta_audience, expires_delta=timedelta(minutes=5))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    validator = JWTValidator(settings, transport=httpx.MockTransport(handler))
    claims = await validator.validate(token)
    await validator.close()

    assert claims["aud"] == settings.okta_audience


@pytest.mark.asyncio
async def test_jwt_validation_fails_on_invalid_audience(settings) -> None:
    private_key, jwk = build_signing_material()
    token = build_token(private_key, settings, audience="api://wrong", expires_delta=timedelta(minutes=5))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    validator = JWTValidator(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await validator.validate(token)
    await validator.close()

    assert exc_info.value.code == "invalid_audience"


@pytest.mark.asyncio
async def test_jwt_validation_fails_on_expired_token(settings) -> None:
    private_key, jwk = build_signing_material()
    token = build_token(private_key, settings, audience=settings.okta_audience, expires_delta=timedelta(seconds=-1))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    validator = JWTValidator(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as exc_info:
        await validator.validate(token)
    await validator.close()

    assert exc_info.value.code == "expired_token"
