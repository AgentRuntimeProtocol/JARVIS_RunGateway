# JARVIS Run Gateway

First-party OSS reference implementation of the ARP `spec/v1` Run Gateway.

This JARVIS component implements the Run Gateway API using the SDK packages:
`arp-standard-server`, `arp-standard-model`, and `arp-standard-client`.

Implements: ARP Standard `spec/v1` Run Gateway API (contract: `ARP_Standard/spec/v1/openapi/run-gateway.openapi.yaml`).

## Requirements

- Python >= 3.11

## Install

```bash
python3 -m pip install arp-jarvis-rungateway
```

## Local configuration (optional)

For local dev convenience, copy the example env file:

```bash
cp .env.example .env.local
```

`src/scripts/dev_server.sh` auto-loads `.env.local` (or `.env`).

## Run

- Run Gateway listens on `http://127.0.0.1:8080` by default.

```bash
python3 -m pip install -e .
arp-jarvis-rungateway
```

> [!TIP]
> Use `bash src/scripts/dev_server.sh --host ... --port ... --reload` for dev convenience.

## Using this repo

This repo is the maintained JARVIS reference for the Run Gateway.

To customize behavior, edit:
- `src/jarvis_run_gateway/gateway.py` (incoming API handlers)
- `src/jarvis_run_gateway/run_coordinator_client.py` (gateway → coordinator client behavior)

### Default behavior

- The gateway requires a configured Run Coordinator at startup.
- All run lifecycle methods forward to the coordinator (no local fallback).
- The gateway validates inbound JWTs and exchanges them for coordinator-scoped tokens.

### Common extensions

- Customize outbound auth (token caching, mTLS) between gateway and coordinator.
- Add gateway-side validation/quotas before forwarding.

## Implementation overview

Request flow:
1) Inbound request hits the Run Gateway (`arp-standard-server`).
2) Auth middleware validates the `Authorization: Bearer <JWT>` header.
3) Gateway captures the inbound bearer token and forwards the call to the coordinator.
4) Gateway exchanges the inbound token for a coordinator-scoped token (or uses client-credentials when no token is present in dev/optional mode).
5) Coordinator processes the request and the gateway returns the response.

Key implementation details:
- Stateless gateway: no local run storage or caching.
- Coordinator is required at startup; the gateway fails fast if missing.
- Token exchange uses `arp-auth` (OIDC client credentials + RFC 8693 token exchange).
- NDJSON streams are proxied as opaque bytes (no rewrite).

## Quick health check

```bash
curl http://127.0.0.1:8080/v1/health
```

## Configuration

CLI flags:
- `--host` (default `127.0.0.1`)
- `--port` (default `8080`)
- `--reload` (dev only)

Environment variables:
- `JARVIS_RUN_COORDINATOR_URL`: base URL for the Run Coordinator (example: `http://127.0.0.1:8081`). Required at startup.
- `JARVIS_RUN_COORDINATOR_AUDIENCE`: audience for token exchange (default: `arp-run-coordinator`).
- `ARP_AUTH_CLIENT_ID` / `ARP_AUTH_CLIENT_SECRET`: required for STS token exchange for outbound coordinator calls.
- `ARP_AUTH_ISSUER`: OIDC issuer (required unless `ARP_AUTH_TOKEN_ENDPOINT` is set).
- `ARP_AUTH_TOKEN_ENDPOINT`: optional override for the STS token endpoint.

## Validate conformance (`arp-conformance`)

Once the service is running, validate it against the ARP Standard:

```bash
python3 -m pip install arp-conformance
arp-conformance check run-gateway --url http://127.0.0.1:8080 --tier smoke
arp-conformance check run-gateway --url http://127.0.0.1:8080 --tier surface
```

## Helper scripts

- `src/scripts/dev_server.sh`: run the server (flags: `--host`, `--port`, `--reload`).

  ```bash
  bash src/scripts/dev_server.sh --host 127.0.0.1 --port 8080
  ```

- `src/scripts/send_request.py`: start a run from a JSON file and fetch the run back.

  ```bash
  python3 src/scripts/send_request.py --request src/scripts/request.json
  ```

## Authentication

Auth is enabled by default (JWT). To disable for local dev, set `ARP_AUTH_PROFILE=dev-insecure`.
If no `ARP_AUTH_*` env vars are set, the gateway defaults to required JWT auth with the dev Keycloak issuer.

To enable local Keycloak defaults, set:
- `ARP_AUTH_PROFILE=dev-secure-keycloak`
- `ARP_AUTH_AUDIENCE=arp-run-gateway`
- `ARP_AUTH_ISSUER=http://localhost:8080/realms/arp-dev`

### Gateway → Coordinator token exchange

The gateway exchanges the incoming bearer token for a coordinator-scoped token before forwarding.
This uses `arp-auth` and requires `ARP_AUTH_CLIENT_ID`/`ARP_AUTH_CLIENT_SECRET`.

If no inbound token is present (only possible when `ARP_AUTH_MODE=optional` or `disabled`),
the gateway falls back to client-credentials to obtain a service token. This is intended for
dev/internal usage only; production should keep `ARP_AUTH_MODE=required`.

### External user tokens (Keycloak broker)

If user tokens come from an external IdP but exchange should happen at Keycloak STS:

```bash
ARP_AUTH_MODE=required
ARP_AUTH_ISSUER=https://idp.example.com/oidc

ARP_AUTH_TOKEN_ENDPOINT=https://keycloak.example.com/realms/arp-dev/protocol/openid-connect/token
ARP_AUTH_CLIENT_ID=arp-run-gateway
ARP_AUTH_CLIENT_SECRET=...

JARVIS_RUN_COORDINATOR_AUDIENCE=arp-run-coordinator
JARVIS_RUN_COORDINATOR_URL=https://coordinator.example.com
```

Keycloak must be configured to trust the external IdP and allow token exchange for the subject token.

## Upgrading

When upgrading to a new ARP Standard SDK release, bump pinned versions in `pyproject.toml` (`arp-standard-*==...`) and re-run conformance.
