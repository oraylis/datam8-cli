# Backend Contract (Canonical)

This document is the canonical HTTP contract between the DataM8 Python backend (`datam8-cli`) and the v2 frontend.
It describes this development checkout and its pinned schema, not every published
beta runtime. See [connector development](connectors.md) for the Python interface.

## Startup and readiness

Electron starts the backend as a long-lived process:

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

Solution, Base and Model JSON files are read and written as UTF-8; generated text
output and v1 migration output are also written as UTF-8 without a BOM. Before
loading a solution, the backend checks its `.dm8s` and the JSON files under its
configured Base and Model paths (including `.properties.json`). Files that cannot
be decoded as UTF-8 are converted from Windows-1252 after JSON validation and
atomically replaced without retaining backup files. UTF-8/ASCII files remain unchanged;
plugins, templates, Python files and existing output are outside this conversion.
Conversion failures identify the affected path and stop loading.

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

The implemented route surface is authoritative. Workspace selection in browser
mode reads the solution bound at server startup; entering another path does not
switch workspaces.

## Desktop workspace switching

`serve --workspace-switch` opts a token-authenticated, loopback server into desktop
workspace switching. Without this flag, workspace management returns 403 and the
startup-bound browser behavior remains unchanged. The initial solution is still
loaded at server startup; switching does not start a second interpreter.

- `GET /workspace` returns `{ "workspaceId": "...", "path": "..." }`.
- `POST /workspace/open` accepts `{ "path": "absolute/path/to/solution.dm8s" }`
  and returns the same envelope after successful activation. Opening the active
  path is idempotent. Non-absolute paths and non-`.dm8s` files return 400.
- Requests in this mode, except health, version and `GET /workspace`, must supply
  `X-DataM8-Workspace` with the workspace ID they were created for. A missing or
  stale ID returns 409 before accessing workspace state. The open request carries
  the old ID; a successful switch returns a new ID.
- Workspace operations are serialized through response completion, including
  save, import, generation and switching. A switch with unsaved model changes
  returns 409. Consumers must flush editor autosaves before opening another path.
- Candidate model and plugin manifests are loaded before activation. Load failure
  restores the prior model, paths, plugins and secret scope and keeps its ID.
  A successful switch releases references to old model/plugin state and clears
  solution-local imported modules and generation registrations.

Electron updates its active path and renderer workspace ID only after success.
Requests and responses belonging to an earlier workspace must not update the new
editor. Runtime configuration changes and process failure may require a restart.

## Entity and function invariants

- Entity rename uses `POST /entities/rename`; model entities and folders use
  `POST /entities/move`.
- Renaming a Base item preserves its existing source JSON file, including custom
  filenames and locations. Changing a Property Value's property also preserves
  that file: the final locator folder denotes its property, not a disk directory.
  Its property field and assignment references change with the locator.
  Other locator folder changes remain explicit moves.
  Property Values are identified by both property and value name when saving.
- Folder moves include the complete subtree and rebase entity, metadata and
  function paths, including the source folder's own `.properties.json`. Folder
  metadata keeps its ID and assignments; its name and relative `path` follow the
  destination. Save metadata under the current name before requesting a rename.
  Saving removes obsolete metadata files and cleans up empty source directories;
  unrelated files keep their source directories in place.
  Function-directory moves are preflighted and rolled back if
  the model move fails. Saving a deleted folder also removes child functions.
- Function source paths are relative to their model entity. Absolute/drive-qualified
  paths, traversal, empty segments and symlink escapes are rejected.
- A bare function filename first resolves beside the entity JSON, then in its
  same-named subdirectory for older solutions. Renaming an entity keeps function
  files in place and persists an explicit relative path when that fallback was used.
- Saving deleted entities also deletes their referenced local function files that
  no surviving entity uses. Missing files are tolerated; shared files, sources
  outside the entity directory and unrelated files are retained. Rename/move copies
  count as surviving entities. Only empty directories are removed afterwards.
- Desktop function creation remains beside the entity JSON and uses the existing
  file bridge with `createOnly: true`. Existing direct or legacy source files cause
  a conflict without overwriting content or committing the transformation change.
- Built-in plugin IDs use `builtin:*`, for example `builtin:SQLServer`.
- Preview requires the plugin capability `previewData`.

## Source import and refresh

- The local CSV builtin treats `path`, `protocol` and `authMode` as connection
  fields, not Polars reader options. Navigation, metadata and preview do not
  consume or mutate the saved connection configuration.
- Source UI behavior is independent of plugin IDs and authentication modes.
  `GET /sources/{data_source}/capabilities` returns connection-specific booleans
  `listSource`, `metadata`, and `previewData`. The optional plugin hook
  `get_source_capabilities()` defaults to implemented methods and manifest capabilities;
  plugins may narrow these for the configured connection. Preview enforces this result.
- Navigation returns `name`, `type`, and an opaque `sourceLocation` for every item.
  `SCHEMA`, `CONTAINER`, and `DIRECTORY` are navigable; other types are selectable.
  All hierarchy levels follow the same rules. Explicit plugin handles and
  `sourceOverride` values are preserved. The backend adapts legacy rows containing
  only `schema`, `container`, or `object`; clients do not construct or parse handles.
- Metadata responses retain `count` and `items`, and add `object` (the existing
  `SourceObject`), the requested `sourceLocation`, and optional `sourceOverride`.
  Clients use the object name and metadata rather than interpreting the handle.
- A non-null import-description entity is authoritative, including display names,
  attributes, sources, relationships, and transformations. Clients may override
  explicitly edited wizard values and the target name/ID, but do not re-map supplied
  types or reconstruct sources. A null entity retains the metadata/mapping fallback;
  it does not trigger backend type resolution. The fallback uses supplied handles
  and source overrides, without connector-specific syntax.
- Builtins include `builtin:OdcsFile` (offline local ODCS 3.2.0 metadata, no preview)
  and `builtin:DatabricksUnityCatalog` (UC metadata and SQL preview).
  See [configuration](builtin-sources.md).
- ODCS contract files are navigable `CONTAINER` entries; directories remain
  `DIRECTORY`. Selected schema objects retain their opaque `<file>#<schema>` handle.
- ODCS supplies `get_sources()` so its import description includes resolved target
  types, business names and the technical object name as a suggested entity name.
  The selected target locator still determines the imported entity name. Plugins
  inheriting `get_sources() -> None` keep their existing import path.
- Source metadata retains its existing schema: `dataType` is the source type.
  ODCS uses `physicalType`, or the declared `logicalType` when no physical type exists.
  Business names enrich existing model fields; no metadata hook overrides target types.
  Plugins may split physical type parameters into length/precision/scale metadata or
  retain parameterized type strings. The backend preserves the supplied source type
  and does not parse dimensions out of it. Dataframe metadata uses `numericScale`;
  serialized `SourceField` currently retains its legacy spelling `numbericScale`.
- Import and complete refresh translate types exclusively using persisted mappings.
  Data Source mappings take precedence over Data Source Type mappings. Each level
  matches the complete type first, then its base type (`DECIMAL(18,2)` matches
  `DECIMAL`, and `STRUCT<...>` matches `STRUCT`). Matching ignores case and surrounding
  whitespace; duplicate keys within one level are rejected. Lookup normalization
  never changes metadata or source types stored in source mappings.
- Missing mappings fail with source, object, column and type context. There is no
  plugin-resolver fallback, implicit canonical-type acceptance or default target.
  Backend import and complete refresh require exactly one Attribute Type whose
  `defaultType` equals the mapped target type and whose `isDefaultProperty` is true.
  No additional Data Types existence lookup is performed by this translation path.
  Clients receiving a non-null import description retain its attribute types.
  The frontend metadata-only path uses the same saved mappings but assigns `Regular`;
  it does not run backend default Attribute Type selection. Source-only refresh does
  not translate target types. Plugin mappings are suggestions copied into the solution
  at binding time, not a runtime substitute for the saved configuration.
- Explicit short builtin IDs alias their canonical `builtin:*` IDs. A data source type
  still requires an explicit `pluginId`; no binding is inferred from its name.
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

## Folder metadata integration

Folder metadata is a direct object in `Model/**/.properties.json`. Use the typed
folder locator with `/entities/{locator}`, then `/model/save` to persist changes.
See the pinned schema's `schema/folder.json` for fields.

The backend validates that a module belongs to the selected product. Folder
properties inherit down the chain; a child overrides a parent by property name.
Product/module context inherits from the nearest applicable ancestor. The UI
displays the effective context while editing the local folder's own values.

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
- coordinated backend + frontend changes,
- integration tests for affected flows.
