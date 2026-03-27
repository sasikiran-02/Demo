"""Agent configuration and initialization."""

import json
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class GatewayConfig:
    """Gateway configuration loaded from gateway_config.json."""
    gateway_url: str
    okta_issuer: str = ""
    okta_client_id: str = ""
    okta_client_secret: str = ""
    okta_scope: str = ""


def load_gateway_config(config_path: Path | None = None) -> GatewayConfig:
    """Load gateway configuration from JSON file."""
    if config_path is None:
        config_path = Path(__file__).with_name("gateway_config.json")

    raw_config: dict = {}
    if config_path.exists() and config_path.stat().st_size > 0:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

    # Extract nested okta config (file values can be overridden by env)
    okta_config = raw_config.get("okta", {})

    gateway_url = raw_config.get("gateway_url") or os.getenv("AGENTCORE_GATEWAY_URL", "")
    if not gateway_url:
        raise ValueError(
            "Missing gateway URL. Set AGENTCORE_GATEWAY_URL in .env or app/agent/gateway_config.json"
        )

    return GatewayConfig(
        gateway_url=gateway_url,
        okta_issuer=okta_config.get("issuer") or os.getenv("OKTA_ISSUER", ""),
        okta_client_id=okta_config.get("client_id") or os.getenv("OKTA_CLIENT_ID", ""),
        okta_client_secret=okta_config.get("client_secret") or os.getenv("OKTA_CLIENT_SECRET", ""),
        okta_scope=okta_config.get("scope") or os.getenv("OKTA_SCOPE", ""),
    )
