# Connectors (Option 3: Connector-driven UI)

DataM8 v2 uses Python connector plugins only. There are no built-in connectors.

## Binding (Variant A)

Connector binding is stored only on `DataSourceType.connectionProperties` using reserved meta property names:

- `__connector.id=<connectorId>` (required, exactly once)
- `__connector.version=<semver|range>` (optional, at most once)

These reserved properties must not be rendered as user inputs in the UI.

`DataSource.extendedProperties` stores only user-entered values as strings.

## Secret handling

Secrets must never be stored plaintext in solution JSON.

- The UI writes a secret reference string into `DataSource.extendedProperties`:
  - `secretRef://runtime/<dataSourceName>/<key>`
- The UI stores the actual secret value in the backend secure store via:
  - `PUT /secrets/runtime`
- Connectors receive a `secret_resolver` that resolves secret references at runtime.

## Plugin loading

The backend discovers connector plugins under `DATAM8_PLUGIN_DIR`:

`$DATAM8_PLUGIN_DIR/connectors/<connector_id>/plugin.json`

The `plugin.json` manifest must include:

- `pluginType: "connector"`
- `id`, `displayName`, `version`
- `entrypoint` (`module.path:ClassName`)
- `capabilities` (at least `uiSchema` and `metadata`)

## API (Neon consumes)

- `GET /connectors`
- `GET /connectors/{connectorId}/ui-schema`
- `POST /connectors/{connectorId}/validate-connection`

## Dev notes

When running `datam8 serve` locally, set `DATAM8_PLUGIN_DIR` to a directory containing a `connectors/` subfolder with connector plugin folders.
