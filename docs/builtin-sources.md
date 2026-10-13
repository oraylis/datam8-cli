# Builtin-Quellen: ODCS und Unity Catalog

Die Plugins `builtin:OdcsFile` und `builtin:DatabricksUnityCatalog` sind Teil von DataM8.
Sie benötigen keine Plugin-Dateien in der Solution und keine zusätzlichen Cloud-SDKs.
Die kurzen IDs `OdcsFile` und `DatabricksUnityCatalog` funktionieren ebenfalls.

## Konfiguration

In `DataSourceTypes.json` wird `pluginId` auf die Builtin-ID gesetzt. Die Definitionen für
`connectionProperties`, `authModes` und `dataTypeMapping` können aus dem Plugin gelesen werden:

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

Die bestehenden API-Endpunkte `/plugins/{plugin_id}/ui-schema`, `/connection-properties`
und `/data-type-mappings` liefern dieselben Definitionen. Beide Quellen benötigen passende
Data Types und pro Zieltyp genau einen Default Attribute Type in der Solution.

### Lokale ODCS-Contracts

Beispiel eines DataSource-Eintrags:

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

`path` kann ein Verzeichnis oder eine einzelne `.yaml`, `.yml` oder `.json`-Datei sein.
Relative Pfade beziehen sich auf den Solution-Ordner. `protocol` hat den Standard `file`;
andere Protokolle werden abgelehnt. Unterverzeichnisse werden über die Source-Navigation geöffnet.
Ein Verzeichnis darf weitere Dateien enthalten; Contracts werden beim Öffnen validiert.
Contract-Dateien werden als aufklappbare `CONTAINER` gemeldet, Verzeichnisse als `DIRECTORY`.

Ein Contract muss `apiVersion: v3.2.0` verwenden. Die Validierung ist offline: das offizielle
Schema und seine Apache-2.0-Lizenz sind im Paket enthalten. YAML wird sicher geladen;
Datumswerte bleiben Strings und doppelte Mapping-Schlüssel werden abgelehnt.

Jedes Schema-Objekt ist separat importierbar. Eine Adresse sieht beispielsweise so aus:

```text
sales/customers.yaml#customers
sales/customers.yaml#Kunden%20Europa
```

Dateipfad und Schema-name werden URL-kodiert, wobei `/` im Dateipfad erhalten bleibt.
Am zuverlässigsten wird die `sourceLocation` aus dem Navigationsergebnis übernommen.
Auch bei einer Einzeldatei enthält die Adresse deren Dateinamen.
`physicalName` hat beim importierten Spaltennamen Vorrang vor `name`.
`businessName` wird zum `displayName`, ohne den technischen Namen zu ersetzen.
Der Wizard übernimmt vollständige Backend-Importbeschreibungen für jedes Plugin einschließlich
Anzeigenamen, Zieltypen, Sources, Beziehungen und Transformationen. Ein expliziter Zielname
ersetzt nur den technischen Entitätsnamen. Liefert ein Plugin keine Importbeschreibung,
verwendet der Wizard die Spaltenmetadaten und konfigurierten Typ-Mappings. Navigation und
Preview richten sich nach den gelieferten Einträgen und Connection-Capabilities.

Der Quelltyp ist `physicalType`; fehlt er, wird der deklarierte `logicalType` verwendet.
Gespeicherte Mappings bestimmen ausschließlich den Zieltyp. Unbekannte physische Typen
benötigen eine explizite Zuordnung; der logische Typ überschreibt sie nicht. Der Quelltyp
bleibt im Source Mapping erhalten. Das Plugin bietet folgende Mapping-Vorschläge für
logische Typen ohne physische Angaben:

| ODCS | DataM8 |
|---|---|
| string | string |
| integer | long |
| number | decimal |
| boolean | bit |
| date | date |
| timestamp | datetime |
| time | time |
| object, array, map, vector | string |

Numerische `format`-Angaben verändern den Zieltyp nicht. Länge sowie physische Decimal-
Präzision und Scale werden weiterhin als Metadaten übernommen.
`maxLength=0` ist in ODCS gültig, wird beim Import aber abgelehnt, weil DataM8 eine positive
Zeichenlänge benötigt. Verschachtelte Unterfelder werden nicht zu weiteren Attributen.

ODCS bietet Metadaten, UI-Schema und Connection-Test. Es bietet keine Datenvorschau.
Quality, SLA, Governance und andere nicht abbildbare Inhalte werden nicht importiert.
Variable Referenzen werden nicht aufgelöst. In benötigten Importfeldern werden sie abgelehnt.

CLI-Beispiele:

```powershell
datam8 sources list Contracts -s .\Example.dm8s
datam8 sources list Contracts sales/customers.yaml -s .\Example.dm8s
datam8 sources metadata Contracts sales/customers.yaml#customers -s .\Example.dm8s
datam8 sources import Contracts sales/customers.yaml#customers modelEntities/Stage/Customers -s .\Example.dm8s
```

## Databricks Unity Catalog

Der Builtin basiert auf `datam8-plugins/plugins/databricks_uc` Version 1.1.0.
Metadaten verwenden die Unity-Catalog-REST-API. Die Vorschau verwendet die SQL Statement
Execution API und benötigt ein SQL Warehouse. Es wird keine Runtime-Extension installiert.

Beispiel mit PAT:

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

Den Secret-Wert zuerst im DataM8-Secret-Store unter `datasources/UC/token` speichern.
Keine Klartext-Credentials in Solution-Dateien ablegen.

| Auth-Modus | Erforderliche Felder |
|---|---|
| pat (Standard) | workspace_url, token als ref:// |
| oauthClientCredentials | workspace_url, client_id, client_secret als ref:// |
| azureServicePrincipal | workspace_url, tenant_id, client_id, client_secret als ref:// |

`catalog` und `schema` sind optionale Navigationsfilter. Bei OAuth ist `auth_scope` optional
mit Standard `all-apis`. Nur bei der Vorschau wird `warehouse_id` oder alternativ
`http_path=/sql/1.0/warehouses/<id>` benötigt. Werden beide angegeben, müssen sie dasselbe
Warehouse bezeichnen. Externe Workspace-URLs verwenden HTTPS.

Source-Locations unterstützen `main.sales.Customers`, `[main.sales].[Customers]`,
`[main].[sales].[Customers]` und `` `main`.`sales`.`Customers` ``.
Spaltenreihenfolge, Kommentare, Nullability, CHAR/VARCHAR-Länge, Decimal-Präzision und Scale
sowie verfügbare Primärschlüssel werden übernommen. ARRAY, MAP, STRUCT und VARIANT werden
zu `string`; der Quelltyp bleibt im Source Mapping erhalten. Constraints werden nicht ausgeführt.

Die Vorschau liefert maximal 1–1000 Zeilen als Anzeigestrings mit erhaltenen Nullwerten.
Authentifizierung, SQL-Anfrage und Inline-Ergebnis-Chunks teilen sich ein Zeitbudget von
30 Sekunden. HTTP-Timeouts und die serverseitige SQL-Wartezeit werden auf die verbleibende
Zeit begrenzt. Bei weniger als fünf verbleibenden Sekunden wird kein neues Statement
gestartet. Ein Cancel-Versuch verwendet ebenfalls nur das verbleibende Zeitbudget.
Berechtigungs-, Authentifizierungs- und Netzwerkfehler geben keine Credential-Werte aus.

```powershell
datam8 sources list UC -s .\Example.dm8s
datam8 sources list UC main.sales -s .\Example.dm8s
datam8 sources preview UC main.sales.Customers --limit 10 -s .\Example.dm8s
datam8 sources import UC main.sales.Customers modelEntities/Stage/Customers -s .\Example.dm8s
```

## Import-Schnittstelle und Refresh

`SourceObject` und `SourceField` behalten ihr bestehendes Schema. `SourceField.dataType`
enthält den physischen Quelltyp; fehlt er im ODCS-Contract, wird der logische Typ verwendet.
Der Backend-Import verwendet gespeicherte Mappings. ODCS übernimmt `businessName` direkt in die
vorhandenen `ModelEntity.displayName`- und `Attribute.displayName`-Felder. Die interne
`TableMetadata`-Implementierung benötigt dafür keine zusätzlichen Schema-Felder.

Der Import speichert Anzeigenamen, Beschreibungen und Typen in den vorhandenen Modellfeldern.
Der vollständige Refresh aktualisiert Quellmetadaten und Source Mappings gemäß dem
[Backend-Vertrag](backend-contract.md#source-import-and-refresh), während lokale
Anzeigenamen und Transformationseinstellungen erhalten bleiben. Neue Attribute übernehmen
ihren Anzeigenamen aus dem Contract. Der Modus `sources-only` aktualisiert ausschließlich
externe Quellen und Mappings.
