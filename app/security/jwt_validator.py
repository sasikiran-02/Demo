from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from app.core.config import Settings
from app.errors import AppError


class JWTValidator:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout_seconds, transport=transport)
        self._jwks_lock = threading.Lock()
        self._refresh_lock = asyncio.Lock()
        self._jwks: dict[str, Any] | None = None
        self._jwks_expiry: datetime | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def validate(self, token: str) -> dict[str, Any]:
        jwks = await self._get_jwks()
        try:
            header = jwt.get_unverified_header(token)
            key_id = header["kid"]
        except (jwt.DecodeError, KeyError) as exc:
            raise AppError(
                stage="validation",
                code="invalid_token_header",
                message="Token header is invalid.",
                status_code=401,
            ) from exc

        jwk = next((candidate for candidate in jwks.get("keys", []) if candidate.get("kid") == key_id), None)
        if not jwk:
            raise AppError(
                stage="validation",
                code="signing_key_not_found",
                message="Matching Okta signing key was not found.",
                status_code=401,
            )

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            return jwt.decode(
                token,
                key=public_key,
                algorithms=[jwk.get("alg", "RS256")],
                audience=self._settings.okta_audience,
                issuer=self._settings.okta_issuer,
                options={"require": ["exp", "nbf", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AppError(
                stage="validation",
                code="expired_token",
                message="Token has expired.",
                status_code=401,
            ) from exc
        except jwt.ImmatureSignatureError as exc:
            raise AppError(
                stage="validation",
                code="token_not_yet_valid",
                message="Token is not valid yet.",
                status_code=401,
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise AppError(
                stage="validation",
                code="invalid_audience",
                message="Token audience does not match the configured audience.",
                status_code=401,
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise AppError(
                stage="validation",
                code="invalid_issuer",
                message="Token issuer does not match the configured issuer.",
                status_code=401,
            ) from exc
        except jwt.InvalidSignatureError as exc:
            raise AppError(
                stage="validation",
                code="invalid_signature",
                message="Token signature validation failed.",
                status_code=401,
            ) from exc
        except jwt.PyJWTError as exc:
            raise AppError(
                stage="validation",
                code="invalid_token",
                message="Token validation failed.",
                status_code=401,
            ) from exc

    async def _get_jwks(self) -> dict[str, Any]:
        now = self._utcnow()
        with self._jwks_lock:
            if self._jwks and self._jwks_expiry and self._jwks_expiry > now:
                return self._jwks

        async with self._refresh_lock:
            now = self._utcnow()
            with self._jwks_lock:
                if self._jwks and self._jwks_expiry and self._jwks_expiry > now:
                    return self._jwks

            try:
                response = await self._client.get(self._settings.okta_jwks_url)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise AppError(
                    stage="validation",
                    code="jwks_timeout",
                    message="Timed out while fetching Okta JWKS.",
                    status_code=504,
                ) from exc
            except httpx.HTTPError as exc:
                raise AppError(
                    stage="validation",
                    code="jwks_fetch_failed",
                    message="Failed to fetch Okta JWKS.",
                    status_code=502,
                ) from exc

            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
                raise AppError(
                    stage="validation",
                    code="jwks_invalid",
                    message="Okta JWKS response is invalid.",
                    status_code=502,
                )

            with self._jwks_lock:
                self._jwks = payload
                self._jwks_expiry = now + timedelta(minutes=5)
                return payload

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)
