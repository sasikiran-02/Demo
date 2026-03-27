from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.errors import AppError
from app.models.schemas import (
    AgentCoreInvokeRequest,
    AgentCoreInvokeResponse,
    ErrorResponse,
    RawAccessTokenResponse,
    TokenMetadataResponse,
    TokenRequest,
)


router = APIRouter(tags=["auth"])


@router.post(
    "/okta/token",
    response_model=TokenMetadataResponse | RawAccessTokenResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def okta_token(request: Request, token_request: TokenRequest) -> TokenMetadataResponse | RawAccessTokenResponse:
    settings = request.app.state.settings
    token_client = request.app.state.okta_client
    token, cached = await token_client.get_token()

    if token_request.access_token_only:
        if not settings.can_expose_raw_access_token:
            raise AppError(
                stage="token",
                code="raw_token_exposure_disabled",
                message="Raw access token exposure is disabled for this environment.",
                status_code=403,
            )
        return RawAccessTokenResponse(access_token=token.access_token)

    now = datetime.now(UTC)
    return TokenMetadataResponse(
        token_type=token.token_type,
        expires_in=token.remaining_seconds(now),
        expires_at=token.expires_at,
        scope=token.scope,
        cached=cached,
    )


@router.post(
    "/agentcore/invoke",
    response_model=AgentCoreInvokeResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def agentcore_invoke(request: Request, invoke_request: AgentCoreInvokeRequest) -> AgentCoreInvokeResponse:
    settings = request.app.state.settings
    token_client = request.app.state.okta_client
    gateway_client = request.app.state.agentcore_client
    validator = request.app.state.jwt_validator

    token, _ = await token_client.get_token()
    validation_performed = False
    if settings.enable_local_token_validation:
        await validator.validate(token.access_token)
        validation_performed = True

    gateway_status, gateway_body = await gateway_client.invoke(invoke_request.payload, token.access_token)
    return AgentCoreInvokeResponse(
        gateway_status=gateway_status,
        gateway_body=gateway_body,
        local_validation_performed=validation_performed,
    )
