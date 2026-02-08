# Jobs (Server-side execution)

The backend uses a minimal, in-memory Job system for any work that can take longer than ~1 second (generation, indexing, validations, etc.). This keeps the Electron UI responsive and avoids HTTP timeouts.

Canonical endpoint and event contract lives in `docs/backend-contract.md`.

## Why Jobs
- Desktop backend is long-lived (spawn once by Electron).
- Work is executed in bounded concurrency (default 2) to avoid overloading the machine.
- The UI consumes status/progress/logs through SSE.

## API contract

### Create
`POST /jobs`

Body:
```json
{ "type": "<jobType>", "params": { } }
```

Response:
```json
{ "jobId": "<id>", "status": "queued" }
```

If the job type is unknown/unimplemented, the server returns a structured error (HTTP 501).

### Inspect
`GET /jobs/{jobId}`

Returns metadata including:
- `status`: `queued|running|succeeded|failed|canceled`
- timestamps
- optional `progress` in `[0..1]`
- optional `result` (on success)
- optional `error` (on failure)

### Cancel (best-effort)
`POST /jobs/{jobId}/cancel`

Cancellation rules:
- `queued` → becomes `canceled` immediately
- `running` → marks `canceled` and attempts to stop the underlying work

### Subscribe (SSE)
`GET /jobs/{jobId}/events`

Events:
- `status` — `{"status":"running"}`
- `log` — `{"message":"...","level":"info"}`
- `progress` — `{"progress":0.42}`
- `result` (final) — `{"result":{...}}`
- `error` (final) — `{"error":{ "code":"...", "message":"...", "details":{...} }}`

SSE messages use:
```text
event: <type>
data: <json>
```

## Implementation notes (contributors)
- Code: `src/datam8/core/jobs/manager.py`
- Job registry is in-memory, bounded by:
  - `max_jobs` (default 50)
  - TTL cleanup (default 1 hour)
- Concurrency is controlled by `DATAM8_JOB_CONCURRENCY` (default 2).

## Adding a new Job type
1) Add a handler in `JobManager._handlers`.
2) Validate `params` early and raise `Datam8ValidationError` for bad input.
3) Emit logs/progress as appropriate.
4) Return a JSON-serializable `result`.
