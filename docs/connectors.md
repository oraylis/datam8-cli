# Connector Plugins

This reference describes the current development Python backend and its pinned
schema. It does not establish compatibility with the recorded desktop beta.6
runtime. See [the backend contract](backend-contract.md#source-import-and-refresh)
for HTTP and refresh semantics and [the offline example](plugin-example.md) for a
complete runnable connector.

The backend includes CSV, SQL Server, Azure Data Lake, local ODCS 3.2.0 and
Databricks Unity Catalog builtins. See [builtin configuration](builtin-sources.md).
SQL and Azure builtins require their corresponding extras.

## Discovery and binding

A custom plugin can live in a solution, a shared repository linked into that
solution, or an installed Python package. It does not need to be added to the
Generator repository. Builtins are distributed with the backend itself.

`Solution.pluginsPath`, relative to the solution folder, contains manifests.
`PluginManager` discovers `**/*.json` below that directory; keep unrelated JSON
files outside it. A manifest uses the case-sensitive `entryPoint` field:

```json
{
  "id": "example:Static",
  "displayName": "Static example",
  "version": "1.0.0",
  "entryPoint": "static_example/plugin.py:ExamplePlugin",
  "capabilities": ["metadata", "uiSchema", "validationConnection"]
}
```

File entry points are relative to `pluginsPath`, not to the manifest's own
directory. Alternatively, use an importable module, such as
`my_connectors.static:ExamplePlugin`, and install its dependencies in the backend
environment. The class and manifest should advertise the same ID and capabilities.

Set `DataSourceType.pluginId` to the manifest ID. The backend does not infer a
plugin from the Data Source Type's name. Connection definitions, auth modes and
saved type mappings belong on the Data Source Type. A concrete Data Source refers
to that type and supplies values through `extendedProperties`; it may also
supply its own type mapping overrides.

Builtin IDs such as `builtin:SQLServer`, `builtin:OdcsFile` and
`builtin:DatabricksUnityCatalog` need no solution plugin files. Explicit short
builtin IDs alias their canonical IDs. Discovery using
`DATAM8_PLUGIN_DIR/connectors`, `pluginType`, `__connector.id` or the old
`/connectors/*` routes belongs to an older architecture.

## Required methods

Subclass [Plugin](../src/datam8/plugins/base.py). The inherited constructor takes
the manifest, Data Source and Data Source Type and validates required connection
properties. Avoid opening a remote connection merely to construct the plugin.

| Method | Form | Responsibility |
| --- | --- | --- |
| `manifest()` | Class method | Return a `PluginManifest` with ID, version, entry point and capabilities |
| `parse_source_location(location)` | Static method | Interpret the connector's own address format; return a tuple of components |
| `resolve_source_type(source_type)` | Class method | Required compatibility method; current import and complete refresh do not call it |
| `get_auth_modes()` | Static method | Return auth modes with connection property names; each mode requires a nonempty `required` list |
| `get_connection_properties()` | Static method | Return field definitions and defaults for connection configuration |
| `get_data_type_mappings()` | Static method | Return suggested physical-to-model mappings, or an empty list when users must configure them |

`get_data_type_mappings()` supplies configuration suggestions. It does not translate
metadata and does not replace mappings already persisted in the solution.
The frontend copies suggestions when binding a plugin to a Data Source Type.
CLI/configuration authors must persist definitions explicitly; merely setting
`pluginId` does not populate them.

Keep `resolve_source_type()` to satisfy the abstract interface and any external
callers that still use it. Do not call it when creating metadata. A connector
that must support older runtimes may need an implementation for those runtimes;
the offline example deliberately rejects calls to demonstrate the current path.

## Optional operations and capabilities

Declare capabilities only for supported operations, and implement the corresponding
methods. The base implementations of navigation, metadata, connection testing and
preview raise errors when those operations are requested without an implementation.

| Method or hook | Return value | Capability and purpose |
| --- | --- | --- |
| `test_connection()` | `Exception \| None` | `validationConnection`; return `None` on success or an error describing failure |
| `list_source(location=None)` | Polars `DataFrame` | `metadata`; list root entries or children of the supplied handle |
| `get_table_metadata(location)` | `TableMetadata` | `metadata`; describe one selectable object |
| `preview_data(location, *, limit=10)` | Polars `LazyFrame` | `previewData`; retrieve actual data with a bounded row count and execution time |
| `get_ui_schema()` | `UiSchema` | `uiSchema`; inherited implementation builds forms from auth modes and connection properties |
| `get_source_capabilities()` | Boolean dictionary | Optional runtime hook; narrow `listSource`, `metadata` and `previewData` for this connection |
| `get_sources(location)` | List of dictionaries or `None` | Optional physical source definitions; no additional manifest capability |
| `TableMetadata.apply_import_metadata(entity)` | `None` | Optional metadata subclass hook to enrich existing model fields, such as display names |

Runtime capabilities default to the implemented operations and declared manifest
capabilities. For example, a connector can expose metadata while disabling preview
until its connection supplies a query endpoint. Clients must use these capabilities
rather than branching on plugin IDs or auth modes.

`apply_import_metadata()` must not override translated data types. It does not add
fields to the serialized `SourceObject` or `SourceField` schema.

## Navigation handles

New plugins should return `name`, `type` and `sourceLocation` for each navigation
entry. Use `SCHEMA`, `CONTAINER` or `DIRECTORY` for entries whose children can be
listed. Other entry types are selectable objects. Return an empty dataframe with
the same column schema when there are no entries.

`sourceLocation` is an opaque connector-owned handle. The frontend passes it
unchanged to navigation, metadata and preview. The plugin handles parsing and
quoting; do not require frontend-specific syntax handling. Metadata's
`SourceObject.name` supplies the technical object name independently of its handle.

The backend's existing compatibility adapter fills handles for legacy rows with
only `schema`, `container` or `object`. Explicit plugin handles are preserved.
Prefer explicit handles for new plugins.

## Metadata fields

Return `TableMetadata(dataframe, SourceObject(...))`, not a dataframe alone.
Metadata describes the object and its columns; it is not a model entity with
already translated target types. Supply rows in ordinal order; conversion preserves
row order rather than sorting it.

| Dataframe column | Required/default | Import meaning |
| --- | --- | --- |
| `name` | Required | Technical attribute and default source column name |
| `ordinal` | Required | One-based `ordinalNumber` |
| `dataType` | Required | Original source type used for configured type matching |
| `isNullable` | Defaults to `true`, including null values | Attribute and source type nullability |
| `isPrimaryKey` | Defaults to `false`, including null values | Imported `isBusinessKey` |
| `maxLength` | Optional | `charLen` |
| `numericPrecision` | Optional | `precision` |
| `numericScale` | Optional | `scale`; preserve zero |
| `description` | Optional | Attribute description |
| `properties` | Optional | Existing property references for attributes and default mappings |

`SourceObject` supplies `name`, `type`, optional `schema`, `description` and
`properties`. Its existing `sourceOverride` is exposed in metadata responses for
compatible clients; it is not a replacement for `get_sources()` in backend imports.
New plugins should use `get_sources()` for physical locations and mappings rather
than introduce another `sourceOverride` path. No `sourceOverride` is needed to
separate metadata and data read locations.

Use the dataframe spelling `numericScale`. The generated `SourceField` and
metadata API currently use the legacy spelling `numbericScale`; `TableMetadata`
bridges these names. Do not change the generated schema to correct the spelling.

For a source `nvarchar(62)`, a plugin may supply `dataType="nvarchar"` and
`maxLength=62`. It may also retain `dataType="nvarchar(62)"`; the matcher can use
its base type. The backend preserves whichever representation the plugin supplies.
It does not strip parameters or extract dimensions. Plugins should supply dimensions
separately when available, including decimal scale 0. Existing ODCS and Unity
Catalog builtins retain their physical type strings and also provide supported
dimensions.

## Saved type translation

Import and complete refresh use saved mappings in this order:

1. Data Source: complete source type, then base type.
2. Data Source Type: complete source type, then base type.

Matching ignores case and surrounding whitespace. For example,
`DECIMAL(18,2)` can match `DECIMAL`, and `STRUCT<...>` can match `STRUCT`.
A Data Source base mapping takes precedence over a Data Source Type exact mapping.
Duplicate normalized keys within either level are errors. Lookup normalization
does not rewrite metadata or persisted source types.

`BIGINT → long` produces an attribute with `dataType.type="long"` and a default
source mapping with `sourceDataType.type="BIGINT"`. A missing mapping fails with
Data Source, object, column and source-type context. There is no plugin-resolver
fallback, implicit acceptance of model-looking types, or replacement with `string`.

Define the mapped types in the solution's Data Types. Backend import currently
does not perform an additional lookup proving that each mapped type is defined
there. It does require exactly one Attribute Type with matching `defaultType`
and `isDefaultProperty=true`. Neither type definitions nor defaults are created
automatically.

CLI/API imports and complete refresh use this backend path. A frontend import
description with a non-null entity is authoritative and is not translated again.
When that description is null, the frontend uses the same saved mapping rules on
metadata, but assigns `Regular` as the Attribute Type. Sources-only refresh does
not change attribute types and does not need target-type translation.

## Optional source definitions

Inherit `get_sources() → None` for a conventional object with one physical source
and identically named columns. Override it when a contract describes different
physical locations or column names:

```python
def get_sources(self, source_location):
    return [
        {
            "sourceLocation": "raw.customers",
            "metadataLocation": "contracts/customers#Customers",
            "sourceName": "customer_id",
            "targetName": "id",
            "sourceAlias": "crm",
            "sourceDataType": {"type": "BIGINT", "nullable": False},
        }
    ]
```

Here `get_table_metadata(source_location)` describes a field named `id` with its
source type; saved mappings still determine the attribute's model type. The hook
supplies the physical source column and optional source type, not a target type.
All rows refer to the selected Data Source, not to a row-level `dataSource`.

Optional keys include `sourceAlias`, `sourceProperties`, `mappingProperties`,
`sourceDataType` and `metadataLocation`. Property references must exist in the
solution. A supplied `sourceDataType` must be a valid model `DataType` object or
dictionary, including both `type` and `nullable`; use the physical source type.
`metadataLocation` is the handle to describe on subsequent refreshes;
`sourceLocation` is the physical read location. A per-row override can point to
another metadata object, and an explicit null opts out of a separate handle.
Omitting `metadataLocation` retains the selected import handle automatically, even
when it differs from the physical `sourceLocation`. `SourceObject.name` remains
the suggested entity name and does not determine either location.

| Result | Meaning |
| --- | --- |
| `None` | Default metadata-derived source/mappings; frontend import-description returns a null entity |
| `[]` | Authoritative empty external-source list; frontend receives a backend entity |
| Nonempty list | Authoritative physical sources/mappings; frontend receives a backend entity |

Authoritative definitions replace external source and mapping properties during
refresh. The default path preserves existing source properties and merges matching
mapping properties. Complete refresh preserves local attribute settings according
to the [canonical ownership rules](backend-contract.md#source-import-and-refresh);
sources-only refresh preserves the entity's attributes, properties, relationships
and transformations.

Import-description and comparison endpoints are read-only previews. The backend
import endpoint creates and saves an entity. Older schema versions without
`metadataLocation` reject documents containing it; use coordinated backend/schema
revisions.

## Connection properties and secrets

Use `ConnectionProperty` to declare fields with types `string`, `number`,
`boolean` or `secret`. Auth modes identify required and optional property names
for generated forms. The base constructor checks globally required connection
properties; implement additional auth-mode-specific validation in your connector.

Access `self.extended_properties` to combine supplied values with Data Source Type
defaults and resolve secret fields. This base property requires
`validationConnection`. Secret references use `ref://`, for example
`ref://datasources/Example/password`; `secretRef://runtime/...` belongs to the
historical architecture. Store secret values through the supported backend secret
workflow, not in solution JSON. Do not log resolved values.

## Verification and compatibility

Run the [offline example](plugin-example.md) before adding transport-specific
logic. For real connectors, verify discovery, instantiation, empty/hierarchical
navigation, metadata fields, dimensions, mapping overrides, errors, save/reload and
both refresh modes on disposable fixtures. Stub remote transport for routine tests;
record live connectivity separately.

Legacy plugins using only `list_schemas()`, `list_tables()` or
`get_table_metadata(table, schema=None)` need an adapter to the current single-handle
methods and `TableMetadata` wrapper. Adding abstract methods alone is insufficient.
A dataframe-like object with only `to_dicts()` is not a `TableMetadata` result.

The [frontend consumer notes](https://github.com/oraylis/datam8-frontend/blob/feature/external_refresh/docs/connectors_dev.md)
explain how the UI uses these results. User workflows belong in the
[central handbook](https://github.com/oraylis/datam8/blob/codex/documentation-v2/docs/user-guide/sources.md).
