from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenRequest(StrictModel):
    access_token_only: bool = False


class TokenMetadataResponse(StrictModel):
    token_type: str
    expires_in: int
    expires_at: datetime
    scope: str | None = None
    cached: bool


class RawAccessTokenResponse(StrictModel):
    access_token: str


class AgentCoreInvokeRequest(StrictModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentCoreInvokeResponse(StrictModel):
    gateway_status: int
    gateway_body: Any
    local_validation_performed: bool


class ErrorDetail(StrictModel):
    stage: str
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail
