from __future__ import annotations

import os
from datetime import datetime, timezone

from arp_standard_server import AuthSettings


def now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized


def run_coordinator_url_from_env() -> str | None:
    url = os.environ.get("ARP_RUN_COORDINATOR_URL")
    if not url:
        return None
    return normalize_base_url(url)


def run_coordinator_bearer_token_from_env() -> str | None:
    token = os.environ.get("ARP_RUN_COORDINATOR_BEARER_TOKEN")
    if not token:
        return None
    return token


def auth_settings_from_env_or_dev_insecure() -> AuthSettings:
    if os.environ.get("ARP_AUTH_MODE") or os.environ.get("ARP_AUTH_PROFILE"):
        return AuthSettings.from_env()
    return AuthSettings(mode="disabled")
