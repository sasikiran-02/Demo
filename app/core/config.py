from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    okta_issuer: str = Field(alias="OKTA_ISSUER")
    okta_client_id: str = Field(alias="OKTA_CLIENT_ID")
    okta_client_secret: SecretStr = Field(alias="OKTA_CLIENT_SECRET")
    okta_scope: str = Field(alias="OKTA_SCOPE")
    okta_audience: str = Field(alias="OKTA_AUDIENCE")
    agentcore_gateway_url: str = Field(alias="AGENTCORE_GATEWAY_URL")
    agentcore_api_key: SecretStr | None = Field(default=None, alias="AGENTCORE_API_KEY")
    enable_local_token_validation: bool = Field(default=False, alias="ENABLE_LOCAL_TOKEN_VALIDATION")
    request_timeout_ms: int = Field(default=5000, alias="REQUEST_TIMEOUT_MS", ge=250)
    environment: Literal["dev", "stage", "prod"] = Field(default="dev", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    expose_raw_access_token: bool = Field(default=False, alias="EXPOSE_RAW_ACCESS_TOKEN")

    @field_validator("okta_issuer", "agentcore_gateway_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value.rstrip("/")

    @property
    def okta_token_url(self) -> str:
        return f"{self.okta_issuer}/v1/token"

    @property
    def okta_jwks_url(self) -> str:
        return f"{self.okta_issuer}/v1/keys"

    @property
    def request_timeout_seconds(self) -> float:
        return self.request_timeout_ms / 1000

    @property
    def request_retry_attempts(self) -> int:
        return {"dev": 1, "stage": 2, "prod": 3}[self.environment]

    @property
    def can_expose_raw_access_token(self) -> bool:
        return self.expose_raw_access_token and self.environment != "prod"

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
