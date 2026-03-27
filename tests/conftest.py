from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        OKTA_ISSUER="https://example.okta.com/oauth2/default",
        OKTA_CLIENT_ID="client-id",
        OKTA_CLIENT_SECRET="client-secret",
        OKTA_SCOPE="agent.invoke",
        OKTA_AUDIENCE="api://default",
        AGENTCORE_GATEWAY_URL="https://agentcore.example.com/invoke",
        AGENTCORE_API_KEY="gateway-key",
        ENABLE_LOCAL_TOKEN_VALIDATION=False,
        REQUEST_TIMEOUT_MS=1000,
        ENVIRONMENT="dev",
        LOG_LEVEL="INFO",
        EXPOSE_RAW_ACCESS_TOKEN=True,
    )
