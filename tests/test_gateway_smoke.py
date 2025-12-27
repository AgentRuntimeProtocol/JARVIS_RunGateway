import asyncio
from typing import cast
from datetime import datetime, timezone

from arp_standard_model import (
    Check,
    Health,
    NodeTypeRef,
    RunGatewayHealthRequest,
    RunGatewayStartRunRequest,
    RunStartRequest,
    RunState,
    Run,
    Status,
)
from arp_standard_server import ArpServerError
from jarvis_run_gateway.gateway import RunGateway
from jarvis_run_gateway.run_coordinator_client import RunCoordinatorGatewayClient


class _FakeCoordinator:
    base_url = "http://coordinator.test"

    async def health(self) -> Health:
        return Health(
            status=Status.degraded,
            time=datetime.now(timezone.utc),
            checks=[Check(name="db", status=Status.down)],
        )

    async def start_run(self, body, *, subject_token=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_run(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def cancel_run(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def stream_run_events(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def test_start_run_requires_coordinator(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("JARVIS_RUN_COORDINATOR_URL", raising=False)
    try:
        RunGateway()
    except RuntimeError as exc:
        assert "Run Coordinator is required" in str(exc)
    else:
        raise AssertionError("Expected gateway init to fail without coordinator")


def test_start_run_forwards_to_coordinator() -> None:
    class _Coordinator:
        base_url = "http://coordinator.test"

        async def start_run(self, body, *, subject_token=None):  # type: ignore[no-untyped-def]
            return Run(
                run_id=body.run_id or "run_test",
                state=RunState.running,
                root_node_run_id="node_run_test",
            )

        async def health(self):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def get_run(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def cancel_run(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        async def stream_run_events(self, run_id, *, subject_token=None):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    gateway = RunGateway(run_coordinator=cast(RunCoordinatorGatewayClient, _Coordinator()))
    start_request = RunGatewayStartRunRequest(
        body=RunStartRequest(
            run_id="run_1",
            root_node_type_ref=NodeTypeRef(node_type_id="composite.echo", version="0.1.0"),
            input={"prompt": "hi"},
        )
    )
    result = asyncio.run(gateway.start_run(start_request))
    assert isinstance(result, Run)
    assert result.run_id == "run_1"


def test_health_propagates_downstream_status() -> None:
    gateway = RunGateway(run_coordinator=cast(RunCoordinatorGatewayClient, _FakeCoordinator()))
    response = asyncio.run(gateway.health(RunGatewayHealthRequest()))

    assert response.status == Status.degraded
    assert response.checks is not None
    assert any(check.name == "run_coordinator" for check in response.checks)


def test_health_degrades_on_exception() -> None:
    class _BadCoordinator:
        base_url = "http://coordinator.test"

        async def health(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    gateway = RunGateway(run_coordinator=cast(RunCoordinatorGatewayClient, _BadCoordinator()))
    response = asyncio.run(gateway.health(RunGatewayHealthRequest()))

    assert response.status == Status.degraded
    assert response.checks is not None
    assert any(check.name == "run_coordinator" for check in response.checks)
