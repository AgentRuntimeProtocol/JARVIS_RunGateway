# ARP Template Run Gateway

Use this repo as a starting point for building an **ARP compliant Run Gateway** service.

This minimal template implements the Run Gateway API using only the SDK packages:
`arp-standard-server`, `arp-standard-model`, and `arp-standard-client`.

It is intentionally small and readable so you can replace the core logic with your own infrastructure while keeping the same API surface.

Implements: ARP Standard `spec/v1` Run Gateway API (contract: `ARP_Standard/spec/v1/openapi/run-gateway.openapi.yaml`).

## Requirements

- Python >= 3.10

## Install

```bash
python3 -m pip install -e .
```

## Local configuration (optional)

For local dev convenience, read, edit and rename the template env file:

```bash
cp .env.example .env.local
```

`src/scripts/dev_server.sh` auto-loads `.env.local` (or `.env`).

## Run

- Run Gateway listens on `http://127.0.0.1:8080` by default.

```bash
python3 -m pip install -e '.[run]'
python3 -m arp_template_run_gateway
```

> [!TIP]
> Use `bash src/scripts/dev_server.sh --host ... --port ... --reload` for dev convenience.

## Using this repo

This template is the minimum viable standalone Run Gateway implementation.

To build your own gateway, fork this repository and replace the in-memory logic with your infrastructure while preserving request/response semantics.

If all you need is to change run lifecycle behavior, edit:
- `src/arp_template_run_gateway/gateway.py` (incoming API handlers)
- `src/arp_template_run_gateway/run_coordinator_client.py` (gateway → coordinator client behavior)

### Default behavior

- If `ARP_RUN_COORDINATOR_URL` is set, the gateway forwards `start/get/cancel/stream` calls to the Run Coordinator.
- If not set, runs are stored in memory (for quick local iteration).

### Common extensions

- Add proper authN/authZ and token exchange for forwarded requests.
- Replace the in-memory fallback with your database or job system.

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
- `ARP_RUN_COORDINATOR_URL`: base URL for the Run Coordinator (example: `http://127.0.0.1:8081`). If set, the gateway proxies requests to it.
- `ARP_RUN_COORDINATOR_BEARER_TOKEN`: optional bearer token used for gateway → coordinator calls.

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

For out-of-the-box usability, this template defaults to auth-disabled unless you set `ARP_AUTH_MODE` or `ARP_AUTH_PROFILE`.

To enable JWT auth, set either:
- `ARP_AUTH_PROFILE=dev-secure-keycloak` + `ARP_AUTH_SERVICE_ID=<audience>`
- or `ARP_AUTH_MODE=required` with `ARP_AUTH_ISSUER` and `ARP_AUTH_AUDIENCE`

## Upgrading

When upgrading to a new ARP Standard SDK release, bump pinned versions in `pyproject.toml` (`arp-standard-*==...`) and re-run conformance.
