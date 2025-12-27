import asyncio
from datetime import datetime, timezone

from arp_standard_model import (
    Check,
    Health,
    NodeTypeRef,
    RunGatewayGetRunParams,
    RunGatewayGetRunRequest,
    RunGatewayHealthRequest,
    RunGatewayStartRunRequest,
    RunStartRequest,
    Status,
)
from arp_template_run_gateway.gateway import RunGateway


class _FakeCoordinator:
    base_url = "http://coordinator.test"

    async def health(self) -> Health:
        return Health(
            status=Status.degraded,
            time=datetime.now(timezone.utc),
            checks=[Check(name="db", status=Status.down)],
        )


def test_start_and_get_run_local() -> None:
    gateway = RunGateway()
    start_request = RunGatewayStartRunRequest(
        body=RunStartRequest(
            run_id="run_1",
            root_node_type_ref=NodeTypeRef(node_type_id="composite.echo", version="0.1.0"),
            input={"prompt": "hi"},
        )
    )
    run = asyncio.run(gateway.start_run(start_request))

    get_request = RunGatewayGetRunRequest(params=RunGatewayGetRunParams(run_id=run.run_id))
    fetched = asyncio.run(gateway.get_run(get_request))

    assert fetched.run_id == run.run_id


def test_health_propagates_downstream_status() -> None:
    gateway = RunGateway(run_coordinator=_FakeCoordinator())
    response = asyncio.run(gateway.health(RunGatewayHealthRequest()))

    assert response.status == Status.degraded
    assert response.checks is not None
    assert any(check.name == "run_coordinator" for check in response.checks)
