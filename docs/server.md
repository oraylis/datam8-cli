# DataM8 Server (`datam8 serve`)

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

## Health/version

No auth required:

- `GET /health` → `{"status":"ok"}`
- `GET /version` → `{"version":"..."}`

## Auth

All endpoints except `/health` and `/version` require:

`Authorization: Bearer <token>`

## Jobs API (heavy work)

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

