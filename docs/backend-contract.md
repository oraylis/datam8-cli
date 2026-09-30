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
- In the desktop launch above, all other endpoints require: `Authorization: Bearer <token>`.
- Implementation note: the CLI currently also accepts an omitted token, which disables
  authentication. Desktop launchers must always provide a non-empty token.

## Current v2 beta route surface

The current `create_app().openapi()` exposes these domains (no `/api` prefix):

- `GET /health` (204), `GET /version` (`schemaVersion`, `appVersion`), `GET /config`.
- `GET /solution`, `GET /solution/full`.
- `GET /entities`, `GET|PUT|PATCH|DELETE /entities/{locator}`, `PUT /entities/clone`,
  `POST /entities/rename`, `POST /entities/move`, `POST /entities/move-single`.
- `POST /model/save`, `POST /model/reload`, `GET /model/unsaved`.
- `POST /model/generate`: optional body `{ "target": "...", "cleanOutput": true,
  "payloads": [] }`; synchronous response `{ "target": "...", "outputPath": "...",
  "message": null }`. Uses the currently loaded solution.
- `/functions/*` for function retrieval, updates and moves.
- `GET /plugins`, `POST /plugins/reload`, `GET /plugins/{plugin_id}` and its
  `/ui-schema`, `/data-type-mappings`, `/connection-properties` subpaths.
- `POST /secrets/check`, `PUT /secrets/set`.
- `/sources/*` for connection checks, navigation, metadata, preview, import and compare;
  see the source section below.

The older Neon parity list below is retained as integration context, **not a list of
available routes in this checkout**. In particular `/generate`, `/fs/list`,
`/connectors/*` and `/model/entities` are not currently registered. This discrepancy
predates source-refresh support; clients must use the implemented surface or coordinate
a separate parity change. The source contract below describes the implemented feature.

## Historical Neon parity surface (not implemented in full)

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
- Model functions: `GET|POST|DELETE /model/function/source`, `POST /model/function/rename`
- Base entities: `GET|POST|DELETE /base/entities`
  - Parity aliases: `GET /base/entity`, `POST /base/entity/set`, `POST /base/entity/patch`
- Solution parity aliases: `GET /solution/info`, `POST /solution/validate`
- Index/refactor: `POST /index/regenerate`, `GET /index/show`, `GET /index/validate`, `POST /refactor/properties`, `POST /refactor/keys`, `POST /refactor/values`, `POST /refactor/entity-id`
- Search: `GET /search/entities`, `GET /search/text`
- Connectors/plugins/secrets under `/connectors/*`, `/plugins/*`, `/datasources/*`, `/http/datasources/*`, `/secrets/*`
  - Datasource parity endpoint: `POST /datasources/{dataSourceId}/test`
  - Plugin parity endpoints: `GET /plugins/{pluginId}/info`, `POST /plugins/{pluginId}/verify`, `POST /plugins/verify`
  - Secrets parity endpoints: `GET /secrets/runtime/list`, `GET /secrets/runtime/key`

### v2 beta compatibility extensions

- Entity rename: `POST /entities/rename`
  - Body: `{ "from": "dataTypes/Text", "to": "dataTypes/String", "content": {} }`
  - Model entities and folders continue to use `POST /entities/move`.
- Entity folder operations include the complete subtree.
  - Moving a folder rebases nested folders, model entities, metadata paths, and function directories.
  - Function-directory moves are preflighted and rolled back if the model move fails.
  - Deleting a folder marks nested folders and model entities for deletion; save also removes their function directories.
- Function source paths are relative to their model entity.
  - Absolute paths, drive-qualified paths, traversal segments, empty segments, and symlink escapes are rejected.
- Built-in plugin IDs use the canonical `builtin:*` form, for example `builtin:SQLServer`.
- `PUT /secrets/set` is an upsert and returns `204 No Content`.
- Canonical source navigation remains under `/sources/{dataSource}/locations`.
- Source metadata may include `description`, `properties`, and `sourceOverride`.
- Preview endpoints require the plugin capability `previewData`.

### Generation

- `POST /generate` (synchronous)
  - Body: `{ "solutionPath": "...", "target": "...", "logLevel": "info", "cleanOutput": true, "payloads": [], "lazy": false }`
  - Response: `{ "status": "succeeded", "target": "...", "outputPath": "..." }`

## Source import and refresh

- Plugins may implement `get_sources(source_location)` and return a list of dictionaries
  with `sourceLocation`, `sourceName`, and `targetName` keys. Optional keys are
  `sourceAlias`, `sourceProperties`, `mappingProperties`, `sourceDataType`, and
  `metadataLocation`. A row's `metadataLocation` overrides the selected import handle
  for that external source.
- `sourceProperties` are assigned to the `ExternalModelSource`; `mappingProperties`
  are assigned to the corresponding `SourceAttributeMapping`.
- `sourceProperties` may be supplied on any one row for a source or repeated with the
  same value on its rows. Conflicting values for the same source are rejected.
- A returned list is authoritative for external sources and mappings. Rows are
  grouped by `(sourceLocation, sourceAlias, metadataLocation)`; omitted source columns
  are not mapped.
- Metadata field names describe target attributes. On import and complete refresh,
  every `targetName` must match a metadata field name; invalid targets are rejected
  before the model is changed. Source-only refresh does not read attribute metadata.
- Returning `None` keeps the default one-source, one-column mapping derived from
  `get_table_metadata()`.
- Complete refresh updates source-owned attribute metadata (data type, description,
  business-key flag and supplied properties), while preserving local expressions,
  display names, history, units, refactor names and deletion markers. Existing
  attribute properties absent from metadata are retained; supplied values take
  precedence by property name. A custom attribute type is retained when the mapped
  data type has not changed.
- An attribute removed from an external mapping is retained if an internal source
  still maps to it. Unmapped, locally modeled attributes are also retained.
- Each imported `ExternalModelSource` may contain `metadataLocation`, the connector
  object used to describe its metadata. `sourceLocation` remains the data read location.
  Several sources may share one `metadataLocation`; refresh describes that contract once.
  Sources without `metadataLocation` continue to use `sourceLocation` for metadata.
- When `get_sources()` supplies definitions during refresh of a legacy source,
  the metadata handle used for that call is retained for subsequent refreshes,
  unless a row explicitly overrides it. The `None` fallback does not add a handle.
- Complete refresh combines distinct attributes and entity properties from every
  contract of the selected entity; conflicting definitions are rejected. A source-only
  refresh replaces the external sources returned by authoritative `get_sources()`
  calls, including their properties and mappings.
- `GET /sources/{data_source}/locations/import-description?source_location=<handle>`
  returns `{ "entity": null }` when the connector does not provide `get_sources()`, or a
  generated `ModelEntity` when the plugin supplies `get_sources()`. The endpoint does not
  save the entity.
- `GET /sources/compare?locator=<locator>` performs the complete refresh and remains
  the default.
- `GET /sources/compare?locator=<locator>&mode=sources-only` refreshes only external
  sources and mappings. Entity attributes, properties, transformations, and
  relationships remain unchanged.

## `GET /solution/full` payload

- `solution`: parsed solution metadata.
- `base_entities`: typed base entity wrappers (`entity` contains the typed entity).
- `model_entities`: model entity wrappers; `locator` is a locator object.
- `folder_entities`: folder entity wrappers from the loaded model.

## Historical Neon folder metadata integration

The save URLs in this section belong to the historical parity surface above; current
entity updates use `/entities/{locator}` followed by `/model/save` where required.

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

- Route implementation is split under `src/datam8/api/routes/` and composed in its
  `__init__.py`; `src/datam8/api/app.py` creates the app and CORS-wrapped server.

## Change policy

Contract changes must include:

- updates to this document,
- coordinated generator + Neon changes,
- integration tests for affected flows.
