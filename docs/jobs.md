# Jobs API (Removed)

As part of the v2 CLI/API cutover, the in-memory Jobs/SSE layer was removed from `datam8-generator`.

Removed endpoints:

- `POST /jobs`
- `GET /jobs/{id}`
- `POST /jobs/{id}/cancel`
- `GET /jobs/{id}/events`

Generation and backend operations now run synchronously via regular HTTP endpoints (for example `POST /generate`).

The canonical active contract is documented in `docs/backend-contract.md`.
