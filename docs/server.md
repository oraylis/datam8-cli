# DataM8 Server (`datam8 serve`)

This document describes the desktop-safe FastAPI backend used by **DataM8 Neon**.

Canonical endpoint contract for Neon lives in `docs/backend-contract.md`.

## Desktop-safe startup protocol

Neon starts the backend as a long-lived process:

```sh
datam8 serve --host 127.0.0.1 --port 0 --token <random>
```

When the server is bound and ready, it prints **exactly one** single-line JSON object to **stdout**:

```json
{"type":"ready","baseUrl":"http://127.0.0.1:<PORT>","version":"<cliVersion>"}
```

All other logs go to **stderr**.

### CLI flags
- `--host` (default `127.0.0.1`) — bind interface (desktop-safe default).
- `--port` (default `0`) — bind port. `0` lets the OS pick a free port.
- `--token` (**required**) — bearer token for all non-health endpoints.
- `--solution-path` (optional) — convenience to set `DATAM8_SOLUTION_PATH` for legacy endpoints.
- `--openapi` (optional) — enables `/docs` and `/openapi.json` (off by default for desktop).

## Health/version

No auth required:

- `GET /health` → `{"status":"ok"}`
- `GET /version` → `{"version":"..."}`

## Auth

All endpoints except `/health` and `/version` require:

`Authorization: Bearer <token>`

If `--token` is missing/blank, the server exits non-zero.

## CORS (dev desktop)
In dev desktop, the UI runs at a Vite origin (typically `http://localhost:4320`) while the backend is `http://127.0.0.1:<port>`.

The server enables CORS for localhost dev by default and supports overrides:
- `DATAM8_CORS_ORIGINS` — comma-separated allowlist (e.g. `http://localhost:4320,http://127.0.0.1:4320`).
- `DATAM8_CORS_ORIGIN_REGEX` — regex allowlist (defaults to `^http://(localhost|127\.0\.0\.1):\d+$`).

## Jobs API (heavy work)

All heavy/slow work is executed via Jobs. The UI should never wait on long synchronous HTTP requests.

Create a job:

`POST /jobs`

```json
{ "type": "generate", "params": { "solutionPath": "...", "target": "..." } }
```

Poll metadata:

- `GET /jobs/{jobId}`

Cancel (best-effort):

- `POST /jobs/{jobId}/cancel`

Stream events (SSE):

- `GET /jobs/{jobId}/events`

Events include: `status`, `log`, `progress`, `result`, `error`.

### SSE format
The endpoint uses Server-Sent Events (SSE). Each message has:
- `event: <type>`
- `data: <json>`

Example:
```text
event: log
data: {"message":"...","level":"info"}
```

### Job types
Supported job types are registered server-side. If a type is not implemented, `POST /jobs` returns a structured error.

Current types:
- `generate` (required)
- `index` (job-ready)
- `validate` (job-ready)
- `pluginVerify` (job-ready)

### Cancellation semantics
Cancel is **best-effort**:
- queued jobs are marked `canceled` immediately
- running jobs are marked canceled and (if subprocess-based) the process tree is terminated

## Error envelope
Errors are returned as a consistent envelope for both validation and server failures.

For auth failures, the server returns HTTP 401 with a `Datam8Error` envelope and a `traceId` if available.

## Code pointers (contributors)
- CLI entrypoint: `src/datam8/cmd/serve.py`
- FastAPI app factory + middleware: `src/datam8/api/app.py`
- Routes:
  - system: `src/datam8/api/routes/system.py`
  - jobs: `src/datam8/api/routes/jobs.py`
  - legacy `/api/*`: `src/datam8/api/routes/legacy_api.py`
