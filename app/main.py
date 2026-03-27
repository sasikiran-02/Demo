from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.auth_routes import router as auth_router
from app.api.agent_routes import router as agent_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.errors import register_exception_handlers
from app.gateway.agentcore_client import AgentCoreGatewayClient
from app.security.jwt_validator import JWTValidator
from app.security.okta_client import OktaTokenClient


def _initialize_state(
    app: FastAPI,
    settings: Settings,
    *,
    okta_transport: httpx.AsyncBaseTransport | None = None,
    jwks_transport: httpx.AsyncBaseTransport | None = None,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    app.state.settings = settings
    app.state.okta_client = OktaTokenClient(settings, transport=okta_transport)
    app.state.jwt_validator = JWTValidator(settings, transport=jwks_transport or okta_transport)
    app.state.agentcore_client = AgentCoreGatewayClient(settings, transport=gateway_transport)


def create_app(
    settings: Settings | None = None,
    *,
    okta_transport: httpx.AsyncBaseTransport | None = None,
    jwks_transport: httpx.AsyncBaseTransport | None = None,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    configured_settings = settings
    application = FastAPI(title="Okta AgentCore Auth Service")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "settings"):
            resolved_settings = configured_settings or get_settings()
            configure_logging(resolved_settings.log_level)
            _initialize_state(
                app,
                resolved_settings,
                okta_transport=okta_transport,
                jwks_transport=jwks_transport,
                gateway_transport=gateway_transport,
            )
        try:
            yield
        finally:
            if hasattr(app.state, "okta_client"):
                await app.state.okta_client.close()
            if hasattr(app.state, "jwt_validator"):
                await app.state.jwt_validator.close()
            if hasattr(app.state, "agentcore_client"):
                await app.state.agentcore_client.close()

    application.router.lifespan_context = lifespan
    if configured_settings is not None:
        configure_logging(configured_settings.log_level)
        _initialize_state(
            application,
            configured_settings,
            okta_transport=okta_transport,
            jwks_transport=jwks_transport,
            gateway_transport=gateway_transport,
        )

    register_exception_handlers(application)
    application.include_router(auth_router)
    application.include_router(agent_router)
    return application


app = create_app()
