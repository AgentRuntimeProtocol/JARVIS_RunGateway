from __future__ import annotations

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
    Status,
    VersionInfo,
)
from arp_standard_server import ArpServerError
from arp_standard_server.run_gateway import BaseRunGatewayServer

from . import __version__
from .request_context import get_bearer_token
from .run_coordinator_client import RunCoordinatorGatewayClient
from .utils import (
    auth_client_from_env,
    now,
    normalize_base_url,
    run_coordinator_audience_from_env,
    run_coordinator_url_from_env,
)


class RunGateway(BaseRunGatewayServer):
    """Run lifecycle ingress; add your authN/authZ and proxying here."""

    # Core method - API surface and main extension points
    def __init__(
        self,
        *,
        run_coordinator: RunCoordinatorGatewayClient | None = None,
        run_coordinator_url: str | None = None,
        service_name: str = "arp-jarvis-rungateway",
        service_version: str = __version__,
    ) -> None:
        """
        Not part of ARP spec; required to construct the gateway.

        Args:
          - run_coordinator: Optional gateway -> coordinator client. If provided,
            `start/get/cancel/stream` calls are proxied to the coordinator.
          - run_coordinator_url: Base URL for the Run Coordinator. Used only if
            `run_coordinator` is not provided. Defaults from `JARVIS_RUN_COORDINATOR_URL`.
          - service_name: Name exposed by /v1/version.
          - service_version: Version exposed by /v1/version.

        Potential modifications:
          - Inject your own RunCoordinatorGatewayClient with custom auth.
          - Replace in-memory fallback with your persistence layer.
          - Add authZ/validation before forwarding requests downstream.
        """
        self._service_name = service_name
        self._service_version = service_version

        if run_coordinator is not None:
            self._run_coordinator = run_coordinator
            return

        if (resolved_url := (run_coordinator_url or run_coordinator_url_from_env())) is None:
            raise RuntimeError("Run Coordinator is required for the Run Gateway")

        resolved_url = normalize_base_url(resolved_url)
        self._run_coordinator = RunCoordinatorGatewayClient(
            base_url=resolved_url,
            auth_client=auth_client_from_env(),
            exchange_audience=run_coordinator_audience_from_env(),
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
        return await self._require_coordinator().start_run(request.body, subject_token=self._subject_token())

    async def get_run(self, request: RunGatewayGetRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayGetRunRequest with run_id.

        Potential modifications:
          - Use your DB/job system as the source of truth instead of memory.
          - Gate visibility (authZ) for multi-tenant environments.
        """
        return await self._require_coordinator().get_run(
            request.params.run_id, subject_token=self._subject_token()
        )

    async def cancel_run(self, request: RunGatewayCancelRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayCancelRunRequest with run_id.

        Potential modifications:
          - Enforce authZ (who can cancel which runs).
          - Add cooperative cancellation and cleanup hooks in your backend.
        """
        return await self._require_coordinator().cancel_run(
            request.params.run_id, subject_token=self._subject_token()
        )

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
        return await self._require_coordinator().stream_run_events(
            request.params.run_id, subject_token=self._subject_token()
        )

    # Helpers (internal): implementation detail for the reference implementation.
    def _require_coordinator(self) -> RunCoordinatorGatewayClient:
        if self._run_coordinator is None:
            raise ArpServerError(
                code="run_coordinator_missing",
                message="Run Coordinator is not configured for this gateway",
                status_code=503,
            )
        return self._run_coordinator

    def _subject_token(self) -> str | None:
        return get_bearer_token()
