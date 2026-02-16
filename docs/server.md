# DataM8 Server (`datam8 serve`)

This document describes the desktop-safe FastAPI backend used by DataM8 Neon.

Canonical endpoint contract for Neon lives in `docs/backend-contract.md`.

## Desktop-safe startup protocol

Neon starts the backend as a long-lived process:

```sh
datam8 serve --host 127.0.0.1 --port 0 --token <random>
```

When the server is bound and ready, it prints exactly one single-line JSON object to stdout:

```json
{"type":"ready","baseUrl":"http://127.0.0.1:<PORT>","version":"<cliVersion>"}
```

All other logs go to stderr.

## CLI flags

- `--host` (default `127.0.0.1`): bind interface (desktop-safe default).
- `--port` (default `0`): bind port. `0` lets the OS pick a free port.
- `--token` (required): bearer token for all non-health endpoints.
- `--solution-path` (optional): convenience to set `DATAM8_SOLUTION_PATH`.
- `--openapi` (optional): enables `/docs` and `/openapi.json` (off by default for desktop).
- `--log-level` (optional): uvicorn log level (`debug|info|warning|error|critical`).

## CLI architecture

- Single CLI root: `src/datam8/app.py`
- Command groups: `src/datam8/cmd/*.py`
- `serve` is one regular command module (`src/datam8/cmd/serve.py`) and shares the same root CLI entry as all other commands.

## Health/version

No auth required:

- `GET /health` -> `{"status":"ok"}`
- `GET /version` -> `{"version":"..."}`

## Auth

All endpoints except `/health` and `/version` require:

`Authorization: Bearer <token>`

If `--token` is missing/blank, the server exits non-zero.

## CORS (dev desktop)

In dev desktop, the UI runs at a Vite origin (typically `http://localhost:4320`) while the backend is `http://127.0.0.1:<port>`.

The server enables CORS for localhost dev by default and supports overrides:

- `DATAM8_CORS_ORIGINS`: comma-separated allowlist.
- `DATAM8_CORS_ORIGIN_REGEX`: regex allowlist (default `^http://(localhost|127\.0\.0\.1):\d+$`).

## Generation flow

Generation is synchronous:

- `POST /generate`
- Request body: `{"solutionPath":"...","target":"...","logLevel":"info","cleanOutput":true}`
- Response body: `{"status":"succeeded","target":"...","outputPath":"..."}`

## Error envelope

Errors are returned as a consistent envelope for both validation and server failures.

For auth failures, the server returns HTTP 401 with a `Datam8Error` envelope and a `traceId` when available.

## Code pointers (contributors)

- CLI entrypoint: `src/datam8/cmd/serve.py`
- CLI root and command registration: `src/datam8/app.py`
- FastAPI app factory + middleware: `src/datam8/api/app.py`
- Routes:
  - system: `src/datam8/api/routes/system.py`
  - workspace/connectors/generate: `src/datam8/api/routes/api.py`
