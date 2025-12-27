import asyncio
from types import SimpleNamespace

import pytest

from arp_standard_client.errors import ArpApiError
from arp_standard_model import NodeTypeRef, RunStartRequest
from arp_standard_server import ArpServerError
from jarvis_run_gateway.run_coordinator_client import RunCoordinatorGatewayClient


class _OkAuth:
    def client_credentials(self, *, audience=None, scope=None):  # type: ignore[no-untyped-def]
        return SimpleNamespace(access_token="svc-token")

    def exchange_token(self, *, subject_token, audience=None, scope=None):  # type: ignore[no-untyped-def]
        return SimpleNamespace(access_token="exchanged-token")


class _RawClient:
    def with_headers(self, headers):  # type: ignore[no-untyped-def]
        return self


class _BaseClient:
    def __init__(self) -> None:
        self.raw_client = _RawClient()


def _run_start_request() -> RunStartRequest:
    return RunStartRequest(
        root_node_type_ref=NodeTypeRef(node_type_id="composite.echo", version="0.1.0"),
        input={"prompt": "hi"},
    )


def test_exchange_token_failure() -> None:
    class _ExchangeError(Exception):
        error = "invalid_request"
        error_description = "nope"
        details = {"reason": "bad"}
        status_code = 400

    class _BadAuth(_OkAuth):
        def exchange_token(self, *, subject_token, audience=None, scope=None):  # type: ignore[no-untyped-def]
            raise _ExchangeError("fail")

    client = RunCoordinatorGatewayClient(base_url="http://coordinator.test", auth_client=_BadAuth())

    with pytest.raises(ArpServerError) as exc:
        asyncio.run(client._exchange_subject_token("token"))  # type: ignore[attr-defined]
    assert exc.value.code == "token_exchange_failed"
    assert exc.value.status_code == 400
    assert exc.value.details is None


def test_client_credentials_failure() -> None:
    class _CredsError(Exception):
        error = "unauthorized_client"
        error_description = "bad creds"
        details = {"reason": "auth"}
        status_code = 401

    class _BadAuth(_OkAuth):
        def client_credentials(self, *, audience=None, scope=None):  # type: ignore[no-untyped-def]
            raise _CredsError("fail")

    client = RunCoordinatorGatewayClient(base_url="http://coordinator.test", auth_client=_BadAuth())

    with pytest.raises(ArpServerError) as exc:
        asyncio.run(client._client_credentials_token())  # type: ignore[attr-defined]
    assert exc.value.code == "token_request_failed"
    assert exc.value.status_code == 401
    assert exc.value.details is None


def test_api_error_passthrough() -> None:
    class _ApiErrorClient:
        def start_run(self, request):  # type: ignore[no-untyped-def]
            raise ArpApiError("bad_request", "nope", status_code=418, details={"x": "y"})

    client = RunCoordinatorGatewayClient(
        base_url="http://coordinator.test",
        client=_BaseClient(),  # type: ignore[arg-type]
        auth_client=_OkAuth(),
        client_factory=lambda raw_client: _ApiErrorClient(),
    )

    with pytest.raises(ArpServerError) as exc:
        asyncio.run(client.start_run(_run_start_request()))
    assert exc.value.code == "bad_request"
    assert exc.value.status_code == 418
    assert exc.value.details == {"x": "y"}


def test_unexpected_error_maps_to_unavailable() -> None:
    class _BoomClient:
        def get_run(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    client = RunCoordinatorGatewayClient(
        base_url="http://coordinator.test",
        client=_BaseClient(),  # type: ignore[arg-type]
        auth_client=_OkAuth(),
        client_factory=lambda raw_client: _BoomClient(),
    )

    with pytest.raises(ArpServerError) as exc:
        asyncio.run(client.get_run("run_1"))
    assert exc.value.code == "run_coordinator_unavailable"
    assert exc.value.details["run_coordinator_url"] == "http://coordinator.test"
