# Backend Contract (Canonical)

This document is the canonical HTTP contract between `datam8-generator` and `datam8-neon`.

## Startup and readiness

Neon starts the backend as a long-lived process:

```bash
datam8 serve --host 127.0.0.1 --port 0 --token <random>
```

When ready, the server writes exactly one JSON line to stdout:

```json
{"type":"ready","baseUrl":"http://127.0.0.1:<PORT>","version":"<cliVersion>"}
```

All non-readiness logs are written to stderr.

## Auth

- No auth required: `GET /health`, `GET /version`, `GET /api/health`
- All other endpoints require: `Authorization: Bearer <token>`

## Endpoints required by Neon

### System

- `GET /health`
- `GET /version`
- `GET /api/health` (compat)
- `GET /api/config`

### Jobs + SSE

- `POST /jobs`
  - Body: `{ "type": "<jobType>", "params": { ... } }`
  - Response: `{ "jobId": "<id>", "status": "queued" }`
- `GET /jobs/{jobId}`
- `POST /jobs/{jobId}/cancel`
- `GET /jobs/{jobId}/events` (`text/event-stream`)

Supported job types used by Neon:

- `generate`
- `index`
- `validate`
- `pluginVerify`

### Workspace `/api/*` surface used by Neon

- Filesystem: `GET /api/fs/list`
- Solution: `GET /api/solution`, `GET /api/solution/full`, `POST /api/solution/new-project`, `POST /api/migration/v1-to-v2`
- Model entities: `GET|POST|DELETE /api/model/entities`, `POST /api/model/entities/move`, `POST /api/model/folder/rename`
- Model functions: `GET|POST /api/model/function/source`, `POST /api/model/function/rename`
- Base entities: `GET|POST|DELETE /api/base/entities`
- Index/refactor: `POST /api/index/regenerate` (legacy compatibility), `POST /api/refactor/properties`
- Connectors/plugins/secrets APIs under `/api/connectors/*`, `/api/plugins/*`, `/api/datasources/*`, `/api/http/datasources/*`, `/api/secrets/*`

## SSE event format

SSE stream payloads are emitted as:

```text
event: <type>
data: <json>
```

Current event types:

- `status` with `{"status":"queued|running|succeeded|failed|canceled"}`
- `log` with `{"stream":"stdout|stderr","message":"..."}`
- `progress` with `{"progress":0.0..1.0}`
- `result` with `{"result":{...}}`
- `error` with `{"error":{"code":"...","message":"...","details":...}}`

The stream closes after a terminal `status` event.

## Change policy

Contract changes must include:

- updates to this document,
- coordinated generator + Neon changes,
- tests that cover `POST /jobs` + SSE completion for affected flows.
