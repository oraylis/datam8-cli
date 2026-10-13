# Build an Offline Connector

This example targets the current development backend and its pinned schema, not
the recorded desktop beta.6 runtime. Read [the plugin reference](connectors.md)
for interface details. It needs Python 3.12+ and a prepared backend checkout;
follow [installation](../README.md) and [testing setup](../tests/README.md).

## Create a disposable solution

The complete example consists of a [manifest](examples/connector/manifest.json),
[plugin implementation](examples/connector/plugin.py), and
[solution setup script](examples/connector/create_solution.py).
The plugin returns static metadata and requires no database, driver or credentials.

From the backend repository, choose a directory that does not yet exist:

```powershell
uv run python docs/examples/connector/create_solution.py C:/Temp/datam8-plugin-demo
```

The script refuses existing directories. It creates this layout:

```text
Example.dm8s
Base/
  DataTypes.json
  AttributeTypes.json
  DataSourceTypes.json
  DataSources.json
  Zones.json
Model/Stage/
Plugins/static_example/
  manifest.json
  plugin.py
```

The demo target only supplies type definitions. This example exercises source
import, not generation; it does not install templates or a deployment target.

## What the plugin supplies

The manifest declares metadata, connection validation and generated UI forms.
Its entry point is relative to the solution's `pluginsPath`, not the manifest's
own directory. The class implements all abstract methods and supplies a
`no_auth` mode with a default `dataset` connection property.

Navigation advertises one object with the opaque handle `demo:customers`.
Metadata supplies `BIGINT`, `nvarchar` and `DECIMAL`, without translating them
to model types. It supplies length 62 separately for the text column and precision
18, scale 0 separately for the decimal column.

The setup script copies the plugin's suggested mappings into the Data Source Type
once: `BIGINT → long`, `nvarchar → string`, and `DECIMAL → decimal`.
It also creates the corresponding model Data Types and exactly one default
Attribute Type for each mapped type. It creates a non-default `Regular` Attribute
Type for the frontend's metadata import path. These fixture definitions belong to
this disposable example; connecting a real plugin does not create them automatically.

The compatibility method `resolve_source_type()` deliberately raises an error.
Successful import and refresh therefore demonstrate that the current backend uses
saved mappings rather than invoking that method.

## Inspect and import with the CLI

Run these commands from the prepared backend checkout:

```powershell
$env:PYTHONUTF8 = "1"
uv run datam8 sources list Demo --solution C:/Temp/datam8-plugin-demo/Example.dm8s
uv run datam8 sources metadata Demo "demo:customers" --solution C:/Temp/datam8-plugin-demo/Example.dm8s
uv run datam8 sources import Demo "demo:customers" modelEntities/Stage/Customers --solution C:/Temp/datam8-plugin-demo/Example.dm8s
uv run datam8 sources refresh modelEntities/Stage/Customers --solution C:/Temp/datam8-plugin-demo/Example.dm8s
```

The UTF-8 setting keeps Python's table output readable when PowerShell redirects
or captures stdout on Windows.

The import creates `Model/Stage/Customers.json`; each CLI invocation loads the
solution from disk. Refresh should report no changes.

| Column | Attribute type | Model data type | Source data type | Dimensions |
| --- | --- | --- | --- | --- |
| id | Defaultlong | long | BIGINT | Non-nullable; business key |
| title | Defaultstring | string | nvarchar | charLen 62 |
| amount | Defaultdecimal | decimal | DECIMAL | precision 18, scale 0 |

The target locator names the entity `Customers`; metadata suggests `customers`.
Inspect the saved JSON and reload it before treating the import as verified.

## Use it in the frontend

Start the matching backend against `Example.dm8s` and connect the development
frontend as described in [the server guide](server.md). Choose **Add Entity → Import
from Source → External**, select Demo, load the listed object and create an entity
with a different target name so it does not collide with the CLI import.

This minimal plugin inherits `get_sources() → None`. The import-description API
therefore returns a null entity, and the frontend uses metadata plus saved type
mappings. Its attributes use `Regular`, while CLI and backend imports select the
default Attribute Type by mapped model type. Both paths preserve source types and
dimensions. Preview is disabled because this plugin does not declare or implement it.

## Extend the example

Add connections and secrets through the definitions described in
[connection configuration](connectors.md#connection-properties-and-secrets).
For hierarchical navigation, advertise containers and return their children for
the supplied handle. Implement preview only when actual data is available.

Override `get_sources()` when metadata describes a contract whose physical columns
or read locations differ. See [source definitions](connectors.md#optional-source-definitions).
Doing so also enables a complete backend import description in the frontend.
A metadata-only connector does not need this hook.
