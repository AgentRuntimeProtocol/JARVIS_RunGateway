from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from arp_auth import AuthClient
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

class RunCoordinatorGatewayClient:
    """Outgoing Run Coordinator client wrapper for the Run Gateway.

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
        client: RunCoordinatorClient | None = None,
        auth_client: AuthClient,
        exchange_audience: str | None = None,
        exchange_scope: str | None = None,
        client_factory: Callable[[Any], RunCoordinatorClient] | None = None,
    ) -> None:
        self.base_url = base_url
        self._client = client or RunCoordinatorClient(base_url=base_url)
        self._auth_client = auth_client
        self._exchange_audience = exchange_audience
        self._exchange_scope = exchange_scope
        self._client_factory = client_factory or (lambda raw_client: RunCoordinatorClient(client=raw_client))

    # Core methods - outgoing Run Coordinator calls
    async def cancel_run(self, run_id: str, *, subject_token: str | None = None) -> Run:
        return await self._call(
            "cancel_run",
            RunCoordinatorCancelRunRequest(params=RunCoordinatorCancelRunParams(run_id=run_id)),
            subject_token=subject_token,
        )

    async def get_run(self, run_id: str, *, subject_token: str | None = None) -> Run:
        return await self._call(
            "get_run",
            RunCoordinatorGetRunRequest(params=RunCoordinatorGetRunParams(run_id=run_id)),
            subject_token=subject_token,
        )

    async def health(self) -> Health:
        return await self._call(
            "health",
            RunCoordinatorHealthRequest(),
        )

    async def start_run(self, body: RunStartRequest, *, subject_token: str | None = None) -> Run:
        return await self._call(
            "start_run",
            RunCoordinatorStartRunRequest(body=body),
            subject_token=subject_token,
        )

    async def stream_run_events(self, run_id: str, *, subject_token: str | None = None) -> str:
        return await self._call(
            "stream_run_events",
            RunCoordinatorStreamRunEventsRequest(params=RunCoordinatorStreamRunEventsParams(run_id=run_id)),
            subject_token=subject_token,
        )

    # Helpers (internal): implementation detail for the reference implementation.
    async def _call(self, method_name: str, request: Any, *, subject_token: str | None = None) -> Any:
        client = await self._client_for(subject_token)
        fn: Callable[[Any], Any] = getattr(client, method_name)
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

    async def _client_for(self, subject_token: str | None) -> RunCoordinatorClient:
        bearer_token = await self._resolve_bearer_token(subject_token)
        raw_client = self._client.raw_client.with_headers({"Authorization": f"Bearer {bearer_token}"})
        return self._client_factory(raw_client)

    async def _resolve_bearer_token(self, subject_token: str | None) -> str:
        if subject_token:
            return await self._exchange_subject_token(subject_token)
        return await self._client_credentials_token()

    async def _exchange_subject_token(self, subject_token: str) -> str:
        try:
            token = await asyncio.to_thread(
                self._auth_client.exchange_token,
                subject_token=subject_token,
                audience=self._exchange_audience,
                scope=self._exchange_scope,
            )
        except Exception as exc:
            raise ArpServerError(
                code="token_exchange_failed",
                message="Token exchange failed",
                status_code=getattr(exc, "status_code", None) or 502,
                details=self._auth_error_details(exc),
            ) from exc
        return token.access_token

    async def _client_credentials_token(self) -> str:
        try:
            token = await asyncio.to_thread(
                self._auth_client.client_credentials,
                audience=self._exchange_audience,
                scope=self._exchange_scope,
            )
        except Exception as exc:
            raise ArpServerError(
                code="token_request_failed",
                message="Client credentials token request failed",
                status_code=getattr(exc, "status_code", None) or 502,
                details=self._auth_error_details(exc),
            ) from exc
        return token.access_token

    def _auth_error_details(self, exc: Exception) -> dict[str, Any] | None:
        _ = exc
        return None
