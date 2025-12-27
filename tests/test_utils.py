import pytest

from jarvis_run_gateway.utils import auth_client_from_env, run_coordinator_audience_from_env


def test_run_coordinator_audience_default(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_RUN_COORDINATOR_AUDIENCE", raising=False)
    assert run_coordinator_audience_from_env() == "arp-run-coordinator"


def test_run_coordinator_audience_override(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_RUN_COORDINATOR_AUDIENCE", "custom-aud")
    assert run_coordinator_audience_from_env() == "custom-aud"


def test_auth_client_from_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("ARP_AUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("ARP_AUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ARP_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("ARP_AUTH_TOKEN_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError):
        auth_client_from_env()


def test_auth_client_from_env_valid(monkeypatch) -> None:
    monkeypatch.setenv("ARP_AUTH_CLIENT_ID", "arp-run-gateway")
    monkeypatch.setenv("ARP_AUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ARP_AUTH_TOKEN_ENDPOINT", "http://sts.test/token")

    client = auth_client_from_env()
    assert client is not None
    assert client._token_endpoint == "http://sts.test/token"
