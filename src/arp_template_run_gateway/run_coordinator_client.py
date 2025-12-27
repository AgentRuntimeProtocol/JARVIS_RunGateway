from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from arp_standard_client.errors import ArpApiError
from arp_standard_client.run_coordinator import RunCoordinatorClient
from arp_standard_model import (
    Health,
    Run,
    RunCoordinatorCancelRunParams,
    RunCoordinatorCancelRunRequest,
    RunCoordinatorGetRunParams,
    RunCoordinatorGetRunRequest,
    RunCoordinatorHealthRequest,
    RunCoordinatorStartRunRequest,
    RunCoordinatorStreamRunEventsParams,
    RunCoordinatorStreamRunEventsRequest,
    RunStartRequest,
)
from arp_standard_server import ArpServerError

T = TypeVar("T")


class RunCoordinatorGatewayClient:
    """Outgoing Run Coordinator client wrapper for the Run Gateway template.

    Edit this file to change gateway -> coordinator client behavior:
    - auth token exchange
    - retries/timeouts/circuit breakers
    - header forwarding (correlation IDs, tenant IDs, etc.)
    """

    # Core method - API surface and main extension points
    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str | None = None,
        client: RunCoordinatorClient | None = None,
    ) -> None:
        self.base_url = base_url
        self._client = client or RunCoordinatorClient(base_url=base_url, bearer_token=bearer_token)

    # Core methods - outgoing Run Coordinator calls
    async def cancel_run(self, run_id: str) -> Run:
        return await self._call(
            self._client.cancel_run,
            RunCoordinatorCancelRunRequest(params=RunCoordinatorCancelRunParams(run_id=run_id)),
        )

    async def get_run(self, run_id: str) -> Run:
        return await self._call(
            self._client.get_run,
            RunCoordinatorGetRunRequest(params=RunCoordinatorGetRunParams(run_id=run_id)),
        )

    async def health(self) -> Health:
        return await self._call(
            self._client.health,
            RunCoordinatorHealthRequest(),
        )

    async def start_run(self, body: RunStartRequest) -> Run:
        return await self._call(
            self._client.start_run,
            RunCoordinatorStartRunRequest(body=body),
        )

    async def stream_run_events(self, run_id: str) -> str:
        return await self._call(
            self._client.stream_run_events,
            RunCoordinatorStreamRunEventsRequest(params=RunCoordinatorStreamRunEventsParams(run_id=run_id)),
        )

    # Helpers (internal): implementation detail for the template.
    async def _call(self, fn: Callable[[Any], T], request: Any) -> T:
        try:
            return await asyncio.to_thread(fn, request)
        except ArpApiError as exc:
            raise ArpServerError(
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code or 502,
                details=exc.details,
            ) from exc
        except Exception as exc:
            raise ArpServerError(
                code="run_coordinator_unavailable",
                message="Run Coordinator request failed",
                status_code=502,
                details={
                    "run_coordinator_url": self.base_url,
                    "error": str(exc),
                },
            ) from exc

