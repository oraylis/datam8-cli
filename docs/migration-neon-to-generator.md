# Migration: Neon FastAPI backend → Generator (Option B)

This document maps the current Neon backend surface area and UI call sites to the new **Generator-owned** FastAPI backend + **Job** system.

## Current state (Neon repo)

### Backend implementation (to migrate)

Neon currently ships a Python Core package in `datam8-neon`:

- Server app factory + error envelope: `packages/datam8_cli/datam8_cli/server/app.py`
- HTTP routes: `packages/datam8_cli/datam8_cli/server/routes.py`
- Core logic used by routes: `packages/datam8_cli/datam8_cli/core/*`

### UI call sites (must update if API shape changes)

Endpoints are called directly via `fetch()` using `apiBase` (`apps/web/src/config.ts`):

- Config / health:
  - `GET /api/config` — `apps/web/src/config.ts`
  - `GET /api/health` — used by Electron main process today: `apps/desktop/src/main.ts`
- Solution:
  - `GET /api/solution/inspect` — `apps/web/src/features/solution/solutionLoader.ts`
  - `GET /api/solution/full` — `apps/web/src/features/solution/solutionLoader.ts`
  - `POST /api/solution/new-project` — `apps/web/src/app/NewProjectDialog.tsx`
  - `POST /api/migration/v1-to-v2` — `apps/web/src/features/migration/components/MigrateSolutionV1Wizard.tsx`
- Workspace IO (model/base/function source):
  - `GET/POST/DELETE /api/model/entities` — `apps/web/src/app/AppShell.tsx`, `apps/web/src/features/model/hooks/useModelActions.ts`, `apps/web/src/features/model/components/wizard/useWizardSubmit.ts`
  - `POST /api/model/entities/move` — `apps/web/src/app/AppShell.tsx`
  - `POST /api/model/folder/rename` — `apps/web/src/app/AppShell.tsx`
  - `GET/POST /api/model/function/source` — `apps/web/src/features/model/components/workspace/hooks/useEntityState.ts`, `apps/web/src/features/model/components/workspace/entity-editor/EntityTransformationsEditor.tsx`
  - `POST /api/model/function/rename` — `apps/web/src/features/model/components/workspace/entity-editor/EntityTransformationsEditor.tsx`
  - `GET/POST/DELETE /api/base/entities` — `apps/web/src/app/AppShell.tsx`
  - `GET /api/fs/list` — `apps/web/src/features/fs/FileSystemContext.tsx`
- Indexing / refactor:
  - `POST /api/index/regenerate` — `apps/web/src/app/AppShell.tsx`, `apps/web/src/features/model/hooks/useModelActions.ts`, `apps/web/src/features/model/components/wizard/useWizardSubmit.ts`
  - `POST /api/refactor/properties` — `apps/web/src/app/AppShell.tsx`
- Generator (must become Jobs-only):
  - `POST /api/generator/run` — `apps/web/src/features/generator/GeneratorContext.tsx`
- Connectors / plugins / secrets:
  - `GET /api/connectors` — `apps/web/src/shared/connectors/connectorCatalog.ts`
  - `GET/POST /api/plugins*` — `apps/web/src/shared/connectors/ConnectorPickerDialog.tsx`
  - `POST /api/datasources/{id}/list-tables` — `apps/web/src/features/model/components/wizard/SourceRow.tsx`
  - `POST /api/sources/{name}/tables` (legacy compat) — `apps/web/src/features/model/components/CreateModelEntityWizard.tsx`
  - `POST /api/datasources/{id}/table-metadata` — `apps/web/src/features/model/components/wizard/useWizardSubmit.ts`
  - `POST /api/http/datasources/{id}/virtual-table-metadata` — `apps/web/src/features/model/components/wizard/SourceRow.tsx`
  - `GET /api/datasources/{id}/usages` — `apps/web/src/features/model/components/workspace/base-editor/RefreshSchemasDialog.tsx`
  - `POST /api/datasources/{id}/refresh-external-schemas/preview|apply` — `apps/web/src/features/model/components/workspace/base-editor/RefreshSchemasDialog.tsx`
  - `GET /api/secrets/available` and `GET/PUT/DELETE /api/secrets/runtime` — `apps/web/src/shared/hooks/useRuntimeSecrets.ts`

### Desktop backend lifecycle (must replace)

Current Electron main process starts either a JSON-RPC daemon (`datam8d`) or a debug HTTP server with Python fallbacks:

- `apps/desktop/src/main.ts` (process spawn + fallbacks + RPC plumbing)
- `apps/desktop/src/preload.ts` (transport selection + RPC bridge)
- `apps/web/src/main.tsx` (fetch interception when RPC transport is active)

This must be replaced by a single supported runtime:

- spawn **PyInstaller-bundled** `datam8` binary
- talk via HTTP only
- use token auth (Bearer)

## Target state (Generator repo)

### Serve protocol (desktop-safe)

Neon spawns:

`datam8 serve --host 127.0.0.1 --port 0 --token <random>`

The server prints exactly one readiness JSON line to **stdout**:

`{"type":"ready","baseUrl":"http://127.0.0.1:<PORT>","version":"<cliVersion>"}`

All other logs go to **stderr**.

Public endpoints (no auth):

- `GET /health`
- `GET /version`

All other endpoints require `Authorization: Bearer <token>`.

### Endpoints to migrate (API parity)

Maintain (or re-home with Neon updates) all endpoints currently called by the UI (see list above). We will keep `/api/*` for workspace operations to minimize UI churn, and add new `/jobs*` endpoints for long-running tasks.

### Jobs (new contract)

Job types required for parity + future-proofing:

- `generate` (wired, required)
- `validate` (stub/job-ready)
- `reverse` (stub/job-ready)
- `index` (job-ready; can later replace `/api/index/regenerate`)
- `pluginVerify` (stub/job-ready)

#### Generate params mapping

Old: `POST /api/generator/run` body:

- `solutionPath: string`
- `target: string`
- `logLevel?: string`
- `cleanOutput?: boolean`
- `payloads?: string[]`

New: `POST /jobs` body:

- `type: "generate"`
- `params: { solutionPath, target, logLevel?, cleanOutput?, payloads? }`

Neon must subscribe to `GET /jobs/{jobId}/events` (SSE) to stream logs/progress/status.

## Files to remove/update (hard gates)

Neon repo (runtime code/config):

- Remove all `dm8gen` usage and PATH injection for it.
- Remove any `datam8d` / stdio JSON-RPC transport + fallbacks.
- Remove any Python/venv fallback logic.

Generator repo:

- Replace sample API (`src/datam8/api/sample.py`) with the real FastAPI app + migrated routers.
- Implement in-server Job system (`src/datam8/core/jobs/*`) + `/jobs*` routes.

