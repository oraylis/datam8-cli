# Connector plugins

This backend loads Python plugins from the solution and includes CSV, SQL Server and
Azure Data Lake built-ins. SQL and Azure built-ins require their corresponding extras.
The source import/refresh API is specified in [the backend contract](backend-contract.md#source-import-and-refresh).

## Discovery and binding

`Solution.pluginsPath`, relative to the solution folder, contains plugin manifests.
`PluginManager` discovers `**/*.json` below that directory. Keep unrelated JSON files
outside it. A manifest uses the case-sensitive `entryPoint` field, for example:

```json
{
  "id": "example",
  "displayName": "Example connector",
  "version": "1.0.0",
  "entryPoint": "example/plugin.py:ExamplePlugin",
  "capabilities": ["metadata", "uiSchema", "validationConnection"]
}
```

Bind `DataSourceType.pluginId` to the manifest ID. When omitted, the manager falls
back to the data source type name. Connection properties and type mappings belong
on the data source type; concrete values belong on `DataSource.extendedProperties`.
Built-in manifests use IDs such as `builtin:SQLServer`.

The current manager does not discover plugins using `DATAM8_PLUGIN_DIR/connectors`,
`pluginType`, or `__connector.id` properties. Those describe an older architecture.

## Implementing a plugin

Subclass `datam8.plugins.base.Plugin` and implement its abstract methods:
`manifest`, `parse_source_location`, `resolve_source_type`, `get_auth_modes`,
`get_connection_properties`, and `get_data_type_mappings`.

Metadata navigation uses `list_source(source_location=None)`. Metadata extraction
uses `get_table_metadata(source_location)` and returns `TableMetadata(dataframe,
SourceObject(...))`. The built-in `SqlServer` connector already follows this interface.
Its metadata conversion and validation tests now run instead of being skipped. The dataframe needs `name`, `ordinal`, and `dataType`; optional
columns include description, properties, nullability, primary-key flags, lengths,
precision and `numericScale`. Use the built-in connectors as implementation examples.
Declare capabilities for the operations actually supported; preview requires
`previewData` and returns a Polars lazy frame.

Legacy implementations with only `list_schemas`, `list_tables` and
`get_table_metadata(table, schema=None)` need an adapter: parse the single location
handle, forward to the legacy implementation, and wrap its dataframe in
`TableMetadata`. Adding the abstract methods alone does not complete that migration.
A dataframe-like object exposing only `to_dicts()` is not a `TableMetadata` result.

## Optional source definitions

Existing plugins that implement the current base interface need no new method:
`Plugin.get_sources()` returns `None`, retaining the metadata-derived default mapping.
To describe different physical sources, override it:

```python
def get_sources(self, source_location):
    return [
        {
            "sourceLocation": "raw.customers",
            "sourceName": "customer_id",
            "targetName": "id",
            "sourceAlias": "crm",
            "mappingProperties": [{"property": "extract_mode", "value": "delta"}],
        }
    ]
```

Here `get_table_metadata(source_location)` describes an attribute named `id`.
It describes the target shape, while the hook supplies physical column mappings.
Ensure referenced property definitions and default attribute types exist in the solution.
See the canonical contract for optional keys, grouping, validation and refresh semantics.

`None` and `[]` have different meanings: `None` uses the default mapping; an empty
list supplies no external sources. Authoritative lists replace source and mapping
properties, so manual values there are not automatically retained. In contrast,
the default fallback preserves existing source properties and merges matching mapping
properties. Complete refresh retains local attribute settings and merges attribute
properties as described in the contract.

Use `metadataLocation` for the object the connector can describe on the next refresh.
`sourceLocation` is the physical read location. A per-row override is useful when one
import describes several contracts. An explicit null opts out of a separate handle.
All rows in this hook belong to the selected data source; it does not switch connectors
using a row-level `dataSource` or the older `SourceObject.sourceOverride` field.

`import-description` and `compare` are read-only previews. The import endpoint
(`PUT /sources/{data_source}/import`) adds and saves the new entity. Older backend
versions whose schema lacks `metadataLocation` reject documents containing it; use
coordinated backend/schema versions when sharing saved solutions.

## Secrets and verification

The current secret resolver uses `ref://` references (for example
`ref://datasources/Example/password`), resolved through `Plugin.extended_properties`.
Do not put plaintext credentials into committed solution files or examples.

For a compatibility check, load the actual plugin against both the base and proposed
backend. Verify instantiation, navigation, metadata conversion, import and repeated
refresh. Use disposable data and stub external transport where necessary; distinguish
those checks from live database or workspace verification. Include a plugin inheriting
`get_sources()` unchanged, as well as one returning authoritative definitions.
