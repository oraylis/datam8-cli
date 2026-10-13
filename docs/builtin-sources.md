# ODCS and Unity Catalog Builtins

This page describes the current development backend and its pinned schema, not
the recorded desktop beta.6 runtime. The plugins `builtin:OdcsFile` and
`builtin:DatabricksUnityCatalog` require no external plugin files in the solution
and no additional cloud SDKs. Their short IDs `OdcsFile` and
`DatabricksUnityCatalog` are also accepted.

## Binding and saved mappings

Bind `DataSourceType.pluginId` to the builtin ID. The plugin supplies connection
definitions, auth modes and suggested type mappings. For programmatic configuration:

```python
from datam8.plugins.manager import PluginManager

plugin = PluginManager().get_plugin("builtin:OdcsFile")
definition = {
    "name": "OdcsFile",
    "pluginId": plugin.manifest().id,
    "connectionProperties": [p.to_dict() for p in plugin.get_connection_properties()],
    "authModes": [a.to_dict() for a in plugin.get_auth_modes()],
    "dataTypeMapping": [m.to_dict() for m in plugin.get_data_type_mappings()],
}
```

Persist this definition as a Data Source Type; plugin lookup alone does not save
it. The frontend's plugin binding copies these suggestions. The
`/plugins/{plugin_id}/ui-schema`, `/connection-properties` and
`/data-type-mappings` API subpaths expose the same definitions.

Import and complete refresh use only saved mappings, with Data Source overrides
before Data Source Type mappings. Each level matches the full type before its base
type. See [the matching rules](connectors.md#saved-type-translation).
Complex types map to `string` only when that mapping is configured; it is not a
runtime fallback.

Configure corresponding Data Types in the solution. Backend imports and complete
refresh require exactly one default Attribute Type per mapped target type.
The frontend's metadata-only import instead uses `Regular`. Connecting a builtin
does not create these definitions, and backend type translation currently does
not add a separate check for the target's presence in Data Types.

## Local ODCS contracts

Example Data Source entry, referring to a Data Source Type named `OdcsFile`:

```json
{
  "name": "Contracts",
  "type": "OdcsFile",
  "extendedProperties": {
    "path": "Contracts",
    "protocol": "file"
  }
}
```

The auth mode is `no_auth`. `path` accepts a directory or one `.yaml`, `.yml`
or `.json` file; relative paths resolve from the solution folder. `protocol`
defaults to `file`; other protocols are rejected. Access outside the configured
root is rejected.
Source handles must be relative; Windows drive/root/UNC paths are rejected on
every host, including Linux.

Directory navigation exposes subdirectories and contract files. Directories use
`DIRECTORY`; contract files use navigable `CONTAINER` entries. Opening a contract
lists its schema objects. With a single-file connection, objects appear directly.
Other files in a directory are ignored.

### Validation and addresses

Contracts must use `apiVersion: v3.2.0`. Validation is offline against the bundled,
versioned [official JSON schema](../src/datam8/plugins/builtins/resources/odcs-json-schema-v3.2.0.json).
Its Apache-2.0 license is included with the resource.
YAML is loaded safely, date values remain strings, and duplicate mapping keys are
rejected.

Each schema object is imported separately. Duplicate schema names in one contract,
missing files, invalid contracts and objects without importable columns are errors.
Contract errors identify the file and field path.

Handles include a relative file path and schema name, for example:

```text
sales/customers.yaml#customers
sales/customers.yaml#Kunden%20Europa
```

File paths and schema names are URL-encoded, preserving path separators. Even a
single-file connection includes the filename in its handle. Pass the advertised
`sourceLocation` unchanged rather than constructing it in the frontend.

### Imported metadata

Technical object and column names use `physicalName` when present, otherwise
`name`. The selected target locator still determines the imported entity name.
`businessName` enriches the existing entity/attribute `displayName`; descriptions,
property order, required flags and primary-key flags become descriptions, ordinals,
nullability and business-key flags.

The source type is `physicalType`, or the declared `logicalType` when physical
type is absent. An unknown physical type requires an explicit saved mapping; a
logical type does not override it. The original source type is retained in source
mappings.

The plugin suggests these mappings for logical types without physical types:

| ODCS source type | Suggested model type |
| --- | --- |
| string | string |
| integer | long |
| number | decimal |
| boolean | bit |
| date | date |
| timestamp | datetime |
| time | time |
| object, array, map, vector | string |

It also supplies mappings for supported physical types. Logical numeric
`format` options do not refine the target type. Length uses
`logicalTypeOptions.maxLength`, with physical CHAR/VARCHAR length as a fallback.
Physical DECIMAL/NUMERIC/NUMBER parameters supply precision and scale, including
scale 0. These dimensions are separate metadata even when the source type includes
parentheses. `maxLength=0` is valid ODCS but rejected on import because DataM8
requires a positive `charLen`.

Complex properties remain one attribute; nested properties are not flattened.
Quality rules, SLA, governance, relationships, transformations and other unmapped
contract sections are not imported. Variable references are not resolved and are
rejected in fields required for import. ODCS supports metadata, generated connection
forms and connection testing; it does not provide preview data.

### CLI usage

```powershell
datam8 sources list Contracts --solution ./Example.dm8s
datam8 sources list Contracts "sales/customers.yaml" --solution ./Example.dm8s
datam8 sources metadata Contracts "sales/customers.yaml#customers" --solution ./Example.dm8s
datam8 sources import Contracts "sales/customers.yaml#customers" modelEntities/Stage/Customers --solution ./Example.dm8s
```

## Databricks Unity Catalog

The builtin was adapted from `datam8-plugins/plugins/databricks_uc` version 1.1.0.
Metadata uses the Unity Catalog REST API; preview uses the SQL Statement Execution
API. No workspace runtime extension is installed.

Example PAT connection, referring to a Data Source Type named
`DatabricksUnityCatalog`:

```json
{
  "name": "UC",
  "type": "DatabricksUnityCatalog",
  "extendedProperties": {
    "authMode": "pat",
    "workspace_url": "https://adb-EXAMPLE.azuredatabricks.net",
    "token": "ref://datasources/UC/token",
    "catalog": "main",
    "schema": "sales",
    "warehouse_id": "WAREHOUSE_ID"
  }
}
```

Save the token through DataM8's secret store at `datasources/UC/token` first.
Do not commit plaintext credentials.

| Auth mode | Required fields |
| --- | --- |
| pat (default) | workspace_url, token as a ref:// reference |
| oauthClientCredentials | workspace_url, client_id, client_secret as a ref:// reference |
| azureServicePrincipal | workspace_url, tenant_id, client_id, client_secret as a ref:// reference |

`catalog` and `schema` optionally filter navigation. OAuth `auth_scope`
defaults to `all-apis`. External workspace URLs use HTTPS. Access still depends
on the principal's permissions; a connection test does not prove access to every
table or SQL Warehouse.

### Metadata and source locations

Catalog/schema navigation and table lists support pagination. Source locations
accept `main.sales.Customers`, `[main.sales].[Customers]`,
`[main].[sales].[Customers]` and `` `main`.`sales`.`Customers` ``.
Use returned handles and source overrides for quoted names.

The plugin retains the source's original `type_text`, or `type_name` when
`type_text` is unavailable, without frontend-specific case conversion.
Comments, column order, nullability, CHAR/VARCHAR length, decimal precision/scale
and available primary keys become metadata. ARRAY, MAP, STRUCT and VARIANT have
suggested `string` mappings; their original type strings remain in source mappings.
Constraints are not executed.

### SQL preview

Metadata does not require a SQL Warehouse. Preview requires `warehouse_id` or
`http_path=/sql/1.0/warehouses/<id>`. If both are supplied they must identify the
same warehouse. Connection capabilities disable preview when neither is configured.

Preview accepts a limit from 1 to 1000 and returns display strings while preserving
null values. Authentication, statement submission, polling and inline result chunks
share a 30-second budget. HTTP timeouts and the SQL wait duration are capped by
remaining time. A new statement is not started with fewer than five seconds left.
An attempted cancellation also uses only the remaining budget.

Authentication, permission and network errors do not expose credential values.
A timeout indicates that preview did not finish within this bounded operation;
it does not establish whether metadata navigation is available.

```powershell
datam8 sources list UC --solution ./Example.dm8s
datam8 sources list UC "main.sales" --solution ./Example.dm8s
datam8 sources preview UC "main.sales.Customers" --limit 10 --solution ./Example.dm8s
datam8 sources import UC "main.sales.Customers" modelEntities/Stage/Customers --solution ./Example.dm8s
```

## Import and refresh

`SourceObject` and `SourceField` retain their existing schemas. ODCS business
names enrich existing model fields through `TableMetadata`; there is no
`targetDataType` field or internal target-type override.

ODCS implements source definitions, enabling a complete backend import description
with mapped types and display names. Unity Catalog uses the conventional
metadata-derived path. The generic frontend consumes either path as described in
[the plugin reference](connectors.md#saved-type-translation).

Complete refresh updates source-owned metadata and mappings according to
[the backend ownership rules](backend-contract.md#source-import-and-refresh).
Local display names and transformation settings are retained; new ODCS attributes
receive their contract display names. Sources-only refresh updates external sources
and mappings without changing attribute types or requiring target-type translation.
