from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.errors import AppError


logger = get_logger(__name__)


@dataclass(slots=True)
class CachedToken:
    access_token: str
    token_type: str
    expires_at: datetime
    scope: str | None = None

    def remaining_seconds(self, now: datetime) -> int:
        return max(0, int((self.expires_at - now).total_seconds()))

    def is_usable(self, now: datetime, skew_seconds: int) -> bool:
        return self.expires_at - timedelta(seconds=skew_seconds) > now


class OktaTokenClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self._cache_lock = threading.Lock()
        self._refresh_lock = asyncio.Lock()
        self._cached_token: CachedToken | None = None
        self._refresh_skew_seconds = 30

    async def close(self) -> None:
        await self._client.aclose()

    async def get_token(self, force_refresh: bool = False) -> tuple[CachedToken, bool]:
        now = self._utcnow()
        with self._cache_lock:
            if not force_refresh and self._cached_token and self._cached_token.is_usable(now, self._refresh_skew_seconds):
                return self._cached_token, True

        async with self._refresh_lock:
            now = self._utcnow()
            with self._cache_lock:
                if not force_refresh and self._cached_token and self._cached_token.is_usable(now, self._refresh_skew_seconds):
                    return self._cached_token, True

            fresh_token = await self._fetch_token()
            with self._cache_lock:
                self._cached_token = fresh_token
            return fresh_token, False

    async def _fetch_token(self) -> CachedToken:
        request_data = {
            "grant_type": "client_credentials",
            "scope": self._settings.okta_scope,
        }

        for attempt in range(1, self._settings.request_retry_attempts + 1):
            try:
                response = await self._client.post(
                    self._settings.okta_token_url,
                    data=request_data,
                    auth=(self._settings.okta_client_id, self._settings.okta_client_secret.get_secret_value()),
                )
            except httpx.TimeoutException as exc:
                if attempt == self._settings.request_retry_attempts:
                    raise AppError(
                        stage="token",
                        code="token_timeout",
                        message="Timed out while requesting an Okta access token.",
                        status_code=504,
                    ) from exc
                await asyncio.sleep(0.1 * attempt)
                continue
            except httpx.HTTPError as exc:
                if attempt == self._settings.request_retry_attempts:
                    raise AppError(
                        stage="token",
                        code="token_connection_error",
                        message="Failed to connect to Okta token endpoint.",
                        status_code=502,
                    ) from exc
                await asyncio.sleep(0.1 * attempt)
                continue

            if response.status_code >= 400:
                error = self._map_error(response)
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < self._settings.request_retry_attempts:
                    await asyncio.sleep(0.1 * attempt)
                    continue
                raise error

            payload = response.json()
            expires_in = int(payload.get("expires_in", 0))
            if not payload.get("access_token") or expires_in <= 0:
                raise AppError(
                    stage="token",
                    code="token_response_invalid",
                    message="Okta token response is missing required fields.",
                    status_code=502,
                )

            issued_at = self._utcnow()
            logger.info("Obtained Okta access token metadata with ttl=%s seconds", expires_in)
            return CachedToken(
                access_token=payload["access_token"],
                token_type=payload.get("token_type", "Bearer"),
                expires_at=issued_at + timedelta(seconds=expires_in),
                scope=payload.get("scope"),
            )

        raise AppError(
            stage="token",
            code="token_request_failed",
            message="Unable to obtain Okta access token.",
            status_code=502,
        )

    def _map_error(self, response: httpx.Response) -> AppError:
        payload = self._safe_json(response)
        upstream_code = payload.get("error") or "token_request_failed"
        description = payload.get("error_description") or "Okta token request failed."
        return AppError(
            stage="token",
            code=upstream_code,
            message=description,
            status_code=response.status_code,
            details={"upstream_status": response.status_code},
        )

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)
