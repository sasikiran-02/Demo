# Okta AgentCore Auth Service

Minimal production-oriented FastAPI service focused only on authentication for Okta OAuth2 client-credentials and AWS AgentCore Gateway token forwarding.

## Features

- `POST /okta/token` to obtain a client-credentials token from Okta
- `POST /agentcore/invoke` to fetch an Okta token and forward the request body to AgentCore Gateway
- Optional local JWT validation against Okta JWKS when `ENABLE_LOCAL_TOKEN_VALIDATION=true`
- In-memory token caching with early refresh skew and consistent auth error responses

## Prerequisites

- Python 3.12+
- `uv`

## Startup

```bash
uv sync --dev
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Curl Tests

Token metadata:

```bash
curl -sS -X POST http://127.0.0.1:8000/okta/token \
  -H 'content-type: application/json' \
  -d '{}'
```

Raw token in non-prod only when `EXPOSE_RAW_ACCESS_TOKEN=true`:

```bash
curl -sS -X POST http://127.0.0.1:8000/okta/token \
  -H 'content-type: application/json' \
  -d '{"access_token_only": true}'
```

AgentCore forwarding:

```bash
curl -sS -X POST http://127.0.0.1:8000/agentcore/invoke \
  -H 'content-type: application/json' \
  -d '{"payload": {"message": "ping"}}'
```

## Tests

```bash
uv run pytest
```

## Runbook

### `invalid_client`

- Verify `OKTA_CLIENT_ID` and `OKTA_CLIENT_SECRET`
- Confirm the Okta application is configured for client-credentials

### `invalid_scope`

- Check `OKTA_SCOPE`
- Confirm the scope is granted to the Okta client application

### `invalid_audience`

- Verify `OKTA_AUDIENCE` matches the audience issued by the Okta authorization server
- If local validation is optional in your POC, set `ENABLE_LOCAL_TOKEN_VALIDATION=false` and let AgentCore remain the primary validator

### `expired_token`

- Confirm system time is correct on the service host
- Reduce long request latencies or inspect whether cached tokens are being refreshed too late

### Gateway `401` or `403`

- Confirm AgentCore expects the Okta issuer and audience you configured
- Verify `AGENTCORE_API_KEY` if your gateway requires it
- Compare the returned gateway response body for upstream authorization details
