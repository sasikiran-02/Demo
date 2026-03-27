from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import Settings
from app.errors import AppError


class AgentCoreGatewayClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout_seconds, transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def gateway_url(self) -> str:
        return self._settings.agentcore_gateway_url

    def build_auth_headers(self, access_token: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {access_token}"}
        if self._settings.agentcore_api_key and self._settings.agentcore_api_key.get_secret_value():
            headers["x-api-key"] = self._settings.agentcore_api_key.get_secret_value()
        return headers

    async def invoke(self, payload: dict[str, Any], access_token: str) -> tuple[int, Any]:
        headers = self.build_auth_headers(access_token)

        for attempt in range(1, self._settings.request_retry_attempts + 1):
            try:
                response = await self._client.post(
                    self._settings.agentcore_gateway_url,
                    json=payload,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                if attempt == self._settings.request_retry_attempts:
                    raise AppError(
                        stage="gateway",
                        code="gateway_timeout",
                        message="Timed out while calling AgentCore Gateway.",
                        status_code=504,
                    ) from exc
                await asyncio.sleep(0.1 * attempt)
                continue
            except httpx.HTTPError as exc:
                if attempt == self._settings.request_retry_attempts:
                    raise AppError(
                        stage="gateway",
                        code="gateway_connection_error",
                        message="Failed to connect to AgentCore Gateway.",
                        status_code=502,
                    ) from exc
                await asyncio.sleep(0.1 * attempt)
                continue

            if response.status_code == 401:
                raise AppError(
                    stage="gateway",
                    code="gateway_unauthorized",
                    message="AgentCore Gateway rejected the token.",
                    status_code=401,
                    details={"gateway_status": response.status_code, "gateway_body": self._safe_body(response)},
                )

            if response.status_code == 403:
                raise AppError(
                    stage="gateway",
                    code="gateway_forbidden",
                    message="AgentCore Gateway denied access.",
                    status_code=403,
                    details={"gateway_status": response.status_code, "gateway_body": self._safe_body(response)},
                )

            if response.status_code >= 400:
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < self._settings.request_retry_attempts:
                    await asyncio.sleep(0.1 * attempt)
                    continue
                raise AppError(
                    stage="gateway",
                    code="gateway_request_failed",
                    message="AgentCore Gateway returned an error.",
                    status_code=response.status_code,
                    details={"gateway_status": response.status_code, "gateway_body": self._safe_body(response)},
                )

            return response.status_code, self._safe_body(response)

        raise AppError(
            stage="gateway",
            code="gateway_request_failed",
            message="Unable to complete AgentCore Gateway request.",
            status_code=502,
        )

    @staticmethod
    def _safe_body(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text
