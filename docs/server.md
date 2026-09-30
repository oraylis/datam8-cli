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
- `--token`: supply a non-empty bearer token for desktop use. The CLI currently
  permits omission, which disables auth; it does not enforce the desktop requirement.
- `--solution-path` / `--solution`: active solution; falls back to
  `DATAM8_SOLUTION_PATH` or the current directory.
- `--openapi` (optional): enables `/docs` and `/openapi.json` (off by default for desktop).
- `--log-level` (optional): uvicorn log level (`debug|info|warning|error|critical`).

## CLI architecture

- Single CLI root: `src/datam8/app.py`
- Command groups: `src/datam8/cmd/*.py`
- `serve` is registered in `src/datam8/cmd/root.py` and shares the same root CLI entry as all other commands.

## Health/version

No auth required:

- `GET /health` -> `204 No Content`.
- `GET /version` -> `{"schemaVersion":"...","appVersion":"..."}`; this endpoint
  reads the active solution's schema version, so a loadable solution is required.

## Auth

When a token is supplied, all endpoints except `/health` and `/version` require:

`Authorization: Bearer <token>`

Do not pass a blank token: it enables auth middleware but cannot authenticate protected
requests. The omission behavior above is a pre-existing difference from the desktop contract.

## CORS (dev desktop)

In dev desktop, the UI runs at a Vite origin (typically `http://localhost:4320`) while the backend is `http://127.0.0.1:<port>`.

The server enables CORS for localhost dev by default and supports overrides:

- `DATAM8_CORS_ORIGINS`: comma-separated allowlist.
- `DATAM8_CORS_ORIGIN_REGEX`: regex allowlist (default `^http://(localhost|127\.0\.0\.1):\d+$`).

## Generation flow

For source import/refresh endpoints and property ownership, see the
[canonical source contract](backend-contract.md#source-import-and-refresh).

Generation is synchronous:

- See [the current route surface](backend-contract.md#current-v2-beta-route-surface)
  for the implemented `/model/generate` body and response. The older `/generate`
  parity endpoint is not registered in this checkout.

## Error envelope

Errors are returned as a consistent envelope for both validation and server failures.

For auth failures, the server returns HTTP 401 with a `Datam8Error` envelope and a `traceId` when available.

## Code pointers (contributors)

- CLI entrypoint: `src/datam8/cmd/root.py:serve`
- CLI root and command registration: `src/datam8/app.py`
- FastAPI app factory + middleware: `src/datam8/api/app.py`
- Routes: `src/datam8/api/routes/`; health/version are in `__init__.py`, source
  metadata/import/compare in `sources.py`, and plugin discovery in `plugins.py`.

`create_server()` wraps the entire FastAPI application in CORS middleware, including
unexpected error responses. When embedding the backend, use that server factory;
`create_app()` alone constructs the routes and auth/error handlers without CORS.
Server middleware tests should exercise `server.config.app`. CORS preflight runs
before bearer-token authentication; actual protected requests still require the token.
