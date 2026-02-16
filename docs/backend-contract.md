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

- No auth required: `GET /health`, `GET /version`
- All other endpoints require: `Authorization: Bearer <token>`

## Endpoint surface used by Neon (plus parity extensions)

### System

- `GET /health`
- `GET /version`
- `GET /config`

### Workspace and editor operations

- Filesystem: `GET /fs/list`
- Solution: `GET /solution`, `GET /solution/full`, `GET /solution/inspect`, `POST /solution/new-project`
  - Full model validate parity: `POST /validate`
- Migration: `POST /migration/v1-to-v2`
- Model entities: `GET|POST|DELETE /model/entities`, `POST /model/entities/move`, `POST /model/folder/rename`
  - Parity aliases: `GET /model/entity`, `POST /model/entity/create`, `POST /model/entity/validate`, `POST /model/entity/set`, `POST /model/entity/patch`, `POST /model/entity/duplicate`
  - Folder metadata explicit endpoints: `GET|POST|DELETE /model/folder-metadata`
- Model functions: `GET|POST /model/function/source`, `POST /model/function/rename`
- Base entities: `GET|POST|DELETE /base/entities`
  - Parity aliases: `GET /base/entity`, `POST /base/entity/set`, `POST /base/entity/patch`
- Solution parity aliases: `GET /solution/info`, `POST /solution/validate`
- Index/refactor: `POST /index/regenerate`, `GET /index/show`, `GET /index/validate`, `POST /refactor/properties`, `POST /refactor/keys`, `POST /refactor/values`, `POST /refactor/entity-id`
- Search: `GET /search/entities`, `GET /search/text`
- Connectors/plugins/secrets under `/connectors/*`, `/plugins/*`, `/datasources/*`, `/http/datasources/*`, `/secrets/*`
  - Datasource parity endpoint: `POST /datasources/{dataSourceId}/test`
  - Plugin parity endpoints: `GET /plugins/{pluginId}/info`, `POST /plugins/{pluginId}/verify`, `POST /plugins/verify`
  - Secrets parity endpoints: `GET /secrets/runtime/list`, `GET /secrets/runtime/key`

### Generation

- `POST /generate` (synchronous)
  - Body: `{ "solutionPath": "...", "target": "...", "logLevel": "info", "cleanOutput": true, "payloads": [], "lazy": false }`
  - Response: `{ "status": "succeeded", "target": "...", "outputPath": "..." }`

## `GET /solution/full` payload

- `solution`: parsed solution metadata.
- `baseEntities`: base JSON entities (`content` is a typed base wrapper object).
- `modelEntities`: model JSON entities (excludes folder metadata files; `locator` is a locator object).
- `folderEntities`: folder metadata files discovered under `Model/**/.properties.json`.

## Folder Metadata Contract

- Folder metadata file path: `Model/**/.properties.json`.
- File content is a direct folder object (no `folders[]` wrapper).
- Folder fields used by Neon/backend:
  - `id` (number), `name` (string)
  - optional `displayName`, `description`, `path`
  - optional `properties` (array of `{ property, value }`)
  - optional `dataProduct` (string) and `dataModule` (string)
- Save/update uses `POST /model/entities` or `POST /model/folder-metadata` with `relPath` pointing to `.properties.json`.

### Folder Validation Rules

- `dataModule` requires `dataProduct`.
- `dataProduct` must exist in `Base/DataProducts.json`.
- `dataModule` must exist under the selected `dataProduct` in `Base/DataProducts.json`.

### Folder Inheritance Semantics (UI Consumption)

- Folder `properties` inherit down the folder chain (child overrides parent by `property` key).
- `dataProduct` and `dataModule` inherit from nearest available ancestors.

## Response contract

- All JSON responses are object payloads with stable top-level fields per endpoint.
- No endpoint returns a bare JSON array or untyped ad-hoc dictionary contract.
- `204 No Content` is used for mutation endpoints that intentionally return no body (e.g. secrets upsert/delete).

### Typing policy

- Stable and workflow-critical fields are exposed via explicit typed response models.
- Plugin-/connector-driven payloads with intentionally dynamic shape remain open objects to avoid over-constraining connector implementations.
- Dynamic sections are still wrapped in typed top-level response envelopes to keep endpoint contracts stable.
- Locator fields in model/folder payloads are typed objects:
  - `entityType: string`
  - `folders: string[]`
  - `entityName: string | null`

## Implementation notes (non-contract)

- Route implementation is split by domain (`api_solution.py`, `api_workspace.py`, `api_connectors.py`) and composed in `api.py`.
- This split does not change endpoint URLs; it is a maintainability refactor only.

## Removed surface

The following endpoints are intentionally removed:

- `/jobs` + `/jobs/{id}` + `/jobs/{id}/cancel` + `/jobs/{id}/events`
- Legacy `/api/*` namespace

## Change policy

Contract changes must include:

- updates to this document,
- coordinated generator + Neon changes,
- integration tests for affected flows.
