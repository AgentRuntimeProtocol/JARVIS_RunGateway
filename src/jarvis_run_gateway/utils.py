from __future__ import annotations

import os
from datetime import datetime, timezone

from arp_auth import AuthClient, AuthError
from arp_standard_server import AuthSettings

DEFAULT_DEV_KEYCLOAK_ISSUER = "http://localhost:8080/realms/arp-dev"


def now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized


def run_coordinator_url_from_env() -> str | None:
    url = os.environ.get("JARVIS_RUN_COORDINATOR_URL")
    if not url:
        return None
    return normalize_base_url(url)


def run_coordinator_audience_from_env() -> str | None:
    value = os.environ.get("JARVIS_RUN_COORDINATOR_AUDIENCE")
    if value:
        return value.strip() or None
    return "arp-run-coordinator"


def auth_client_from_env() -> AuthClient:
    try:
        return AuthClient.from_env()
    except AuthError as exc:
        raise RuntimeError(f"Invalid ARP_AUTH_* token exchange config: {exc}") from exc


def _has_auth_env() -> bool:
    return any(key.startswith("ARP_AUTH_") for key in os.environ)


def auth_settings_from_env_or_dev_secure() -> AuthSettings:
    if _has_auth_env():
        return AuthSettings.from_env()
    return AuthSettings(mode="required", issuer=DEFAULT_DEV_KEYCLOAK_ISSUER)
