from __future__ import annotations

import json
import uuid

from arp_standard_model import (
    Check,
    Health,
    Run,
    RunGatewayCancelRunRequest,
    RunGatewayGetRunRequest,
    RunGatewayHealthRequest,
    RunGatewayStartRunRequest,
    RunGatewayStreamRunEventsRequest,
    RunGatewayVersionRequest,
    RunState,
    Status,
    VersionInfo,
)
from arp_standard_server import ArpServerError
from arp_standard_server.run_gateway import BaseRunGatewayServer

from . import __version__
from .run_coordinator_client import RunCoordinatorGatewayClient
from .utils import now, normalize_base_url, run_coordinator_bearer_token_from_env, run_coordinator_url_from_env


class RunGateway(BaseRunGatewayServer):
    """Run lifecycle ingress; add your authN/authZ and proxying here."""

    # Core method - API surface and main extension points
    def __init__(
        self,
        *,
        run_coordinator: RunCoordinatorGatewayClient | None = None,
        run_coordinator_url: str | None = None,
        run_coordinator_bearer_token: str | None = None,
        service_name: str = "arp-template-run-gateway",
        service_version: str = __version__,
    ) -> None:
        """
        Not part of ARP spec; required to construct the gateway.

        Args:
          - run_coordinator: Optional gateway -> coordinator client. If provided,
            `start/get/cancel/stream` calls are proxied to the coordinator.
          - run_coordinator_url: Base URL for the Run Coordinator. Used only if
            `run_coordinator` is not provided. Defaults from `ARP_RUN_COORDINATOR_URL`.
          - run_coordinator_bearer_token: Optional bearer token for coordinator calls.
            Used only if `run_coordinator` is not provided. Defaults from `ARP_RUN_COORDINATOR_BEARER_TOKEN`.
          - service_name: Name exposed by /v1/version.
          - service_version: Version exposed by /v1/version.

        Potential modifications:
          - Inject your own RunCoordinatorGatewayClient with custom auth.
          - Replace in-memory fallback with your persistence layer.
          - Add authZ/validation before forwarding requests downstream.
        """
        self._runs: dict[str, Run] = {}
        self._service_name = service_name
        self._service_version = service_version

        if run_coordinator is not None:
            self._run_coordinator = run_coordinator
            return

        resolved_url = run_coordinator_url or run_coordinator_url_from_env()
        if resolved_url is None:
            self._run_coordinator = None
            return

        resolved_url = normalize_base_url(resolved_url)
        self._run_coordinator = RunCoordinatorGatewayClient(
            base_url=resolved_url,
            bearer_token=run_coordinator_bearer_token or run_coordinator_bearer_token_from_env(),
        )

    # Core methods - Run Gateway API implementations
    async def health(self, request: RunGatewayHealthRequest) -> Health:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayHealthRequest (unused).

        Potential modifications:
          - Add checks for downstream dependencies (Run Coordinator, auth, DB).
          - Report degraded status when dependencies fail.
        """
        _ = request
        if self._run_coordinator is None:
            return Health(status=Status.ok, time=now())

        try:
            downstream_health = await self._run_coordinator.health()
        except Exception as exc:
            check = Check(
                name="run_coordinator",
                status=Status.down,
                message=str(exc),
                details={"url": self._run_coordinator.base_url},
            )
            return Health(status=Status.degraded, time=now(), checks=[check])

        check = Check(
            name="run_coordinator",
            status=downstream_health.status,
            message=None,
            details={
                "url": self._run_coordinator.base_url,
                "status": downstream_health.status,
            },
        )
        checks = [check]
        if downstream_health.checks:
            checks.extend(downstream_health.checks)
        return Health(status=downstream_health.status, time=now(), checks=checks)

    async def version(self, request: RunGatewayVersionRequest) -> VersionInfo:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayVersionRequest (unused).

        Potential modifications:
          - Include build metadata (git SHA, build time) via VersionInfo.build.
        """
        _ = request
        return VersionInfo(
            service_name=self._service_name,
            service_version=self._service_version,
            supported_api_versions=["v1"],
        )

    async def start_run(self, request: RunGatewayStartRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayStartRunRequest with RunStartRequestBody.

        Potential modifications:
          - Validate/normalize external inputs before forwarding.
          - Enforce authZ and/or quotas here (gateway-facing policy).
        """
        if self._run_coordinator is not None:
            return await self._run_coordinator.start_run(request.body)

        run_id = request.body.run_id or f"run_{uuid.uuid4().hex}"
        if run_id in self._runs:
            raise ArpServerError(
                code="run_already_exists",
                message=f"Run '{run_id}' already exists",
                status_code=409,
            )

        root_node_run_id = f"node_run_{uuid.uuid4().hex}"
        run = Run(
            run_id=run_id,
            state=RunState.running,
            root_node_run_id=root_node_run_id,
            run_context=request.body.run_context,
            started_at=now(),
            ended_at=None,
            extensions=request.body.extensions,
        )
        self._runs[run_id] = run
        return run

    async def get_run(self, request: RunGatewayGetRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayGetRunRequest with run_id.

        Potential modifications:
          - Use your DB/job system as the source of truth instead of memory.
          - Gate visibility (authZ) for multi-tenant environments.
        """
        if self._run_coordinator is not None:
            return await self._run_coordinator.get_run(request.params.run_id)
        return self._get_local_run(request.params.run_id)

    async def cancel_run(self, request: RunGatewayCancelRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayCancelRunRequest with run_id.

        Potential modifications:
          - Enforce authZ (who can cancel which runs).
          - Add cooperative cancellation and cleanup hooks in your backend.
        """
        if self._run_coordinator is not None:
            return await self._run_coordinator.cancel_run(request.params.run_id)

        run = self._get_local_run(request.params.run_id)
        if run.state in {RunState.succeeded, RunState.failed, RunState.canceled}:
            return run
        updated = run.model_copy(update={"state": RunState.canceled, "ended_at": now()})
        self._runs[run.run_id] = updated
        return updated

    async def stream_run_events(self, request: RunGatewayStreamRunEventsRequest) -> str:
        """
        Optional (spec): Run event streaming endpoint for the Run Gateway.

        Args:
          - request: RunGatewayStreamRunEventsRequest with run_id.

        Potential modifications:
          - Proxy coordinator events (default when coordinator is configured).
          - Implement your own event store and stream NDJSON lines.
          - Add filtering/redaction for external consumers.
        """
        if self._run_coordinator is not None:
            return await self._run_coordinator.stream_run_events(request.params.run_id)

        payload = {
            "run_id": request.params.run_id,
            "seq": 0,
            "type": "run_started",
            "time": now().isoformat(),
            "data": {"message": "Template Run Gateway does not stream real events yet."},
        }
        return json.dumps(payload) + "\n"

    # Helpers (internal): implementation detail for the template.
    def _get_local_run(self, run_id: str) -> Run:
        """Internal helper for in-memory fallback when no coordinator is configured."""
        run = self._runs.get(run_id)
        if run is None:
            raise ArpServerError(
                code="run_not_found",
                message=f"Run '{run_id}' not found",
                status_code=404,
            )
        return run
