# Backend Contract

This is the canonical HTTP contract between `datam8-generator` and DataM8 clients.

## Startup

The backend is started with:

```sh
datam8 serve --host 127.0.0.1 --port 0 --token <token>
```

After binding, stdout receives one compact JSON line:

```json
{"type":"ready","baseUrl":"http://127.0.0.1:<port>","version":"<version>"}
```

All endpoints except `GET /health` and `GET /version` require
`Authorization: Bearer <token>` when the server was created with a token.

## Response Envelopes

List endpoints return:

```json
{"count":1,"items":[]}
```

Single entity endpoints return:

```json
{"item":{}}
```

Unhandled failures use the `Datam8Error` envelope and do not expose exception
types or internal messages.

## System and Solution

- `GET /health`
- `GET /version`
- `GET /config`
- `GET /solution`
- `GET /solution/full`

## Entities

- `GET /entities/{locator}`
- `PUT /entities/{locator}`
- `PATCH /entities/{locator}`
- `DELETE /entities/{locator}`
- `PUT /entities/clone`
- `POST /entities/rename`
- `POST /entities/move`

Rename request:

```json
{"from":"dataTypes/Text","to":"dataTypes/String","content":{}}
```

Move request:

```json
{"from":"modelEntities/raw/Customer","to":"modelEntities/core/Customer"}
```

Model entities and folders use `move`, not `rename`. Moving a model entity also
moves its function directory. A target function directory conflict returns
HTTP 409 before the in-memory model is changed.

## Model

- `POST /model/generate`
- `POST /model/save`
- `POST /model/reload`
- `GET /model/unsaved`

Generation request:

```json
{"target":"databricks","cleanOutput":true,"payloads":[]}
```

## Function Sources

- `GET /model/function/source?locator=...&source=...`
- `POST /model/function/source`
- `DELETE /model/function/source?locator=...&source=...`
- `POST /model/function/rename`

Write request:

```json
{
  "locator":"modelEntities/core/Customer",
  "source":"helpers/normalize.sql",
  "content":"select 1"
}
```

Rename request:

```json
{
  "locator":"modelEntities/core/Customer",
  "fromSource":"helpers/normalize.sql",
  "toSource":"normalize.sql"
}
```

Function source paths are relative to the selected model entity. Absolute
paths, drive-qualified paths, traversal segments, empty segments and resolved
symlink escapes are rejected with HTTP 400. Missing files return HTTP 404 and
target conflicts return HTTP 409.

## Sources

Canonical source endpoints:

- `GET /sources/{dataSource}/test`
- `GET /sources/{dataSource}/locations`
- `GET /sources/{dataSource}/locations/metadata`
- `GET /sources/{dataSource}/locations/preview`
- `PUT /sources/{dataSource}/import`
- `GET /sources/compare`
- `GET /sources/{dataSource}/usages`

Metadata and preview use the `source_location` query parameter. Canonical import:

```json
{"locator":"modelEntities/raw/Customer","sourceLocation":"dbo.Customer"}
```

Preview requires the plugin capability `previewData`.

Compatibility endpoints for clients using schema/table navigation:

- `GET /sources/{dataSource}/schemas`
- `GET /sources/{dataSource}/schemas/{schema}/tables`
- `GET /sources/{dataSource}/schemas/{schema}/tables/{table}`
- `GET /sources/{dataSource}/schemas/{schema}/tables/{table}/preview`
- `PUT /sources/{dataSource}/schemas/{schema}/tables/{table}/import`
- `GET /sources/{dataSource}/tables`
- `GET /sources/{dataSource}/tables/{table}`
- `GET /sources/{dataSource}/tables/{table}/preview`
- `PUT /sources/{dataSource}/tables/{table}/import`

Compatibility imports take:

```json
{"locator":"modelEntities/raw/Customer"}
```

The compatibility routes are adapters over the canonical plugin methods. They
do not restore the removed SQL-specific plugin interface.

## Plugins and Secrets

- `GET /plugins/`
- `POST /plugins/reload`
- `GET /plugins/{pluginId}`
- `GET /plugins/{pluginId}/ui-schema`
- `GET /plugins/{pluginId}/data-type-mappings`
- `GET /plugins/{pluginId}/connection-properties`
- `POST /secrets/check`
- `PUT /secrets/set`

## Change Policy

Contract changes require a contract update, backend tests and a client
integration check. The generic `/locations` source API remains canonical;
compatibility paths may be removed only after all consumers have migrated.
