from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)


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
            logger.info(
                "Run Gateway configured (run_coordinator_url=%s)",
                getattr(self._run_coordinator, "base_url", "custom"),
            )
            return

        if (resolved_url := (run_coordinator_url or run_coordinator_url_from_env())) is None:
            raise RuntimeError("Run Coordinator is required for the Run Gateway")

        resolved_url = normalize_base_url(resolved_url)
        exchange_audience = run_coordinator_audience_from_env()
        self._run_coordinator = RunCoordinatorGatewayClient(
            base_url=resolved_url,
            auth_client=auth_client_from_env(),
            exchange_audience=exchange_audience,
        )
        logger.info(
            "Run Gateway configured (run_coordinator_url=%s, exchange_audience=%s)",
            resolved_url,
            exchange_audience,
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
        root_ref = request.body.root_node_type_ref
        logger.info(
            "Run start requested (node_type_id=%s, version=%s, input_keys=%s)",
            root_ref.node_type_id,
            root_ref.version,
            _input_key_count(request.body.input),
        )
        try:
            run = await self._require_coordinator().start_run(request.body, subject_token=self._subject_token())
        except ArpServerError as exc:
            logger.warning("Run start failed (%s): %s", exc.code, exc.message)
            raise
        except Exception:
            logger.exception("Run start failed")
            raise
        logger.info(
            "Run started (run_id=%s, root_node_run_id=%s, state=%s)",
            run.run_id,
            run.root_node_run_id,
            run.state,
        )
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
        run_id = request.params.run_id
        logger.info("Run fetch requested (run_id=%s)", run_id)
        try:
            run = await self._require_coordinator().get_run(run_id, subject_token=self._subject_token())
        except ArpServerError as exc:
            logger.warning("Run fetch failed (%s): %s", exc.code, exc.message)
            raise
        except Exception:
            logger.exception("Run fetch failed (run_id=%s)", run_id)
            raise
        logger.info("Run fetched (run_id=%s, state=%s)", run.run_id, run.state)
        return run

    async def cancel_run(self, request: RunGatewayCancelRunRequest) -> Run:
        """
        Mandatory: Required by the ARP Run Gateway API.

        Args:
          - request: RunGatewayCancelRunRequest with run_id.

        Potential modifications:
          - Enforce authZ (who can cancel which runs).
          - Add cooperative cancellation and cleanup hooks in your backend.
        """
        run_id = request.params.run_id
        logger.info("Run cancel requested (run_id=%s)", run_id)
        try:
            run = await self._require_coordinator().cancel_run(run_id, subject_token=self._subject_token())
        except ArpServerError as exc:
            logger.warning("Run cancel failed (%s): %s", exc.code, exc.message)
            raise
        except Exception:
            logger.exception("Run cancel failed (run_id=%s)", run_id)
            raise
        logger.info("Run canceled (run_id=%s, state=%s)", run.run_id, run.state)
        return run

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
        run_id = request.params.run_id
        logger.info("Run events stream requested (run_id=%s)", run_id)
        try:
            payload = await self._require_coordinator().stream_run_events(
                run_id, subject_token=self._subject_token()
            )
        except ArpServerError as exc:
            logger.warning("Run events stream failed (%s): %s", exc.code, exc.message)
            raise
        except Exception:
            logger.exception("Run events stream failed (run_id=%s)", run_id)
            raise
        logger.info("Run events stream ready (run_id=%s, bytes=%s)", run_id, len(payload))
        return payload

    # Helpers (internal): implementation detail for the reference implementation.
    def _require_coordinator(self) -> RunCoordinatorGatewayClient:
        if self._run_coordinator is None:
            logger.error("Run Coordinator is not configured for this gateway")
            raise ArpServerError(
                code="run_coordinator_missing",
                message="Run Coordinator is not configured for this gateway",
                status_code=503,
            )
        return self._run_coordinator


def _input_key_count(payload: object | None) -> int | None:
    if isinstance(payload, dict):
        return len(payload)
    return None

    def _subject_token(self) -> str | None:
        return get_bearer_token()
