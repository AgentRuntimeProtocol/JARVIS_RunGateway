import importlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis_run_gateway.request_context import (
    get_bearer_token,
    parse_bearer_token,
    reset_bearer_token,
    set_bearer_token,
)


def test_parse_bearer_token() -> None:
    assert parse_bearer_token(None) is None
    assert parse_bearer_token("") is None
    assert parse_bearer_token("Token abc") is None
    assert parse_bearer_token("Bearer") is None
    assert parse_bearer_token("Bearer abc") == "abc"
    assert parse_bearer_token("bearer xyz") == "xyz"


def test_bearer_token_context_roundtrip() -> None:
    state = set_bearer_token("token-1")
    try:
        assert get_bearer_token() == "token-1"
    finally:
        reset_bearer_token(state)
    assert get_bearer_token() is None


def test_app_middleware_captures_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_RUN_COORDINATOR_URL", "http://coordinator.test")
    monkeypatch.setenv("ARP_AUTH_PROFILE", "dev-insecure")
    monkeypatch.setenv("ARP_AUTH_CLIENT_ID", "arp-run-gateway")
    monkeypatch.setenv("ARP_AUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ARP_AUTH_TOKEN_ENDPOINT", "http://sts.test/token")

    sys.modules.pop("jarvis_run_gateway.app", None)
    app_mod = importlib.import_module("jarvis_run_gateway.app")
    app: FastAPI = app_mod.create_app()

    @app.get("/_token")
    async def _token():  # type: ignore[no-untyped-def]
        return {"token": get_bearer_token()}

    client = TestClient(app)
    response = client.get("/_token", headers={"Authorization": "Bearer abc123"})
    assert response.json()["token"] == "abc123"

    response = client.get("/_token")
    assert response.json()["token"] is None
