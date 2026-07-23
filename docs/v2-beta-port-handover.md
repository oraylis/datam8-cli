# v2-beta Port Handover

## Kurzfassung

Der Port wurde in beiden Repositories auf einem neuen
`feature/v2-beta-port` vom jeweiligen `main` aufgebaut. Es wurde nichts nach
`main` gemergt oder gepusht. Der Generator referenziert den lokalen
Model-Commit `fcce955`.

Ausgangsstände:

- `datam8-model main`: `3bf6e06`
- `datam8-model feature/v2-beta-port`: `fcce955`
- `datam8-generator main`: `c3e9fee`
- Generator-Implementierungsstand vor dieser Dokumentation: `0bd9b00`
- Vergleichssample `feature/databricks-lakeflow`: `1e1855e`

## Ergebnis

- Model-Schema-Metavalidierung: erfolgreich.
- Model-Contract-Tests: 9 erfolgreich.
- Generator Ruff: erfolgreich, keine Findings.
- Generator Pyright: erfolgreich, keine Findings.
- Neue isolierte Generator-Tests: erfolgreich.
- Gesamtsuite mit kompatiblem Sample: 83 erfolgreich, 1 fehlgeschlagen, 1 übersprungen.
- A/B-Generierung: 93 Dateien mit Beta und Port, kein inhaltlicher Unterschied.

Der eine Fehler der Gesamtsuite ist eine fehlende Sample-Fixture:
`propertyValues/jobs/sales_weekly`. Der übersprungene Test benötigt unter
Windows das Recht zum Erstellen von Symlinks.

Der originale Beta-Generator konnte den A/B-Lauf zunächst nicht starten, weil
er `min_length` auf die interne Relationship-ID `3000` anwendet. Im
temporären Beta-Checkout wurde nur diese eine generierte Typzeile von
`Annotated[int, Field(min_length=1)]` auf `int` korrigiert. Danach erzeugten
Beta und Port exakt denselben Output.

## Empfohlene Review-Reihenfolge

1. Model-Schema und Model-Contract-Tests prüfen.
2. Generator-Submodule und reproduzierbare Codegenerierung prüfen.
3. Relationship-Validator im Codegen-Template prüfen.
4. Entity Rename und Container-Persistenz prüfen.
5. Function-Pfadsicherheit und Move-Rollback prüfen.
6. Source-Metadata und Preview-Capability prüfen.
7. Source-Kompatibilitätsadapter prüfen.
8. Baseline-Typkorrekturen separat prüfen.
9. API-Vertrag und dieses Übergabedokument prüfen.

## Changes für Dummies

### Source Overrides

**Was war vorher?** Ein Plugin konnte nur melden, wo eine Tabelle gefunden
wurde. Der Generator musste genau diese Quelle in das Model übernehmen.

**Was ändert sich?** Ein `SourceObject` darf mit `sourceOverride` eine andere
`dataSource` oder `sourceLocation` für das erzeugte Model vorgeben.

**Warum brauchen wir das?** Ein Discovery-Plugin kann Daten über einen
technischen Katalog finden, während das erzeugte Model auf die tatsächlich zu
verwendende Laufzeitquelle zeigen soll.

**Einfaches Beispiel:** Discovery erfolgt über `sql-crm/dbo.Customer`, aber das
Model erhält `crm-api/customers/current`.

**Was bleibt unverändert?** Ohne Override werden die angefragte Data Source und
Source Location weiterverwendet.

**Risiko:** Ein fehlerhaftes Plugin kann auf eine falsche Quelle umleiten.

**Absicherung:** Schema- und Import-Pipeline-Tests prüfen beide Override-Felder.

**Review-Hinweis:** `schema/data-source.json`, generiertes `data_source.py` und
`datam8/source.py`.

### Source- und Field-Beschreibungen

**Was war vorher?** Beschreibungen aus einem Quellsystem gingen beim Import
verloren.

**Was ändert sich?** Tabellenbeschreibungen landen auf `ModelEntity.description`;
Spaltenbeschreibungen landen auf `Attribute.description`.

**Warum brauchen wir das?** Fachliche Dokumentation wird aus dem Quellsystem in
DataM8 übernommen.

**Einfaches Beispiel:** `Customer master` bleibt nach dem Import als
Entity-Beschreibung erhalten.

**Was bleibt unverändert?** Plugins ohne Beschreibungen liefern weiterhin
`None`.

**Risiko:** Sehr lange oder ungepflegte Quelltexte werden unverändert
übernommen.

**Absicherung:** `TableMetadata` setzt fehlende Beschreibungen kontrolliert auf
`None`; Pipeline-Tests prüfen Tabelle und Feld.

**Review-Hinweis:** `TableMetadata.iter_source_fields()` und
`read_from_data_source()`.

### Externe Relationships

**Was war vorher?** `targetLocation` war immer eine interne numerische
Model-ID.

**Was ändert sich?** Ohne `dataSource` bleibt das Ziel eine Integer-ID. Mit
`dataSource` ist das Ziel ein nicht leerer String.

**Warum brauchen wir das?** Relationships dürfen auf Tabellen außerhalb des
aktuellen DataM8-Models zeigen.

**Einfaches Beispiel:** Intern: `targetLocation: 12`. Extern:
`dataSource: crm`, `targetLocation: dbo.Customer`.

**Was bleibt unverändert?** Bestehende interne Integer-Relationships bleiben
gültig.

**Risiko:** Eine uneindeutige Union könnte Integer und String vertauschen.

**Absicherung:** JSON-Schema-Bedingung, generierter Pydantic-Nachvalidator und
Tests für alle gültigen und ungültigen Kombinationen.

**Review-Hinweis:** `schema/model.json`,
`template/pydantic_v2/BaseModel.jinja2` und generiertes `model.py`.

### Plugin-Capability previewData

**Was war vorher?** Clients konnten nicht erkennen, ob ein Plugin Preview
wirklich unterstützt.

**Was ändert sich?** `previewData` ist eine eigene Capability. Built-ins
bewerben sie nur, wenn sie `preview_data` implementieren.

**Warum brauchen wir das?** Die UI kann Preview-Aktionen korrekt ein- oder
ausblenden.

**Einfaches Beispiel:** CSV, Azure Lake und SQL Server melden
`previewData`; ein reines Metadata-Plugin nicht.

**Was bleibt unverändert?** Metadata und Connection Validation bleiben eigene
Capabilities.

**Risiko:** Ein Plugin könnte die Capability melden, ohne die Methode korrekt
zu implementieren.

**Absicherung:** Die API prüft die Capability und Built-in-Tests prüfen die
Manifeste.

**Review-Hinweis:** `plugins/base.py`, Built-in-Manifeste und Preview-Route.

### UI-Enums

**Was war vorher?** Ein UI-Feld konnte Typ, Label und Default definieren, aber
keine feste Auswahlliste.

**Was ändert sich?** `UiField.enum` akzeptiert eine Liste von Strings.

**Warum brauchen wir das?** Plugins können Dropdowns statt Freitextfeldern
beschreiben.

**Einfaches Beispiel:** `enum: ["sql_user", "windows"]`.

**Was bleibt unverändert?** Felder ohne `enum` funktionieren wie bisher.

**Risiko:** Nicht-String-Werte werden abgelehnt.

**Absicherung:** Model-Contract-Test prüft den Item-Typ.

**Review-Hinweis:** `schema/plugin.json` und generiertes `plugin.py`.

### Optionales pluginsPath

**Was war vorher?** Die Solution musste `pluginsPath` angeben, obwohl bereits
der Default `Plugins` dokumentiert war.

**Was ändert sich?** Das Feld ist optional; der Generator verwendet bei
fehlendem Wert `Plugins`.

**Warum brauchen wir das?** Aktuelle Sample Solutions ohne dieses Feld können
geladen werden.

**Einfaches Beispiel:** Eine Solution mit nur `basePath`, `modelPath` und
Targets sucht Plugins automatisch unter `Plugins`.

**Was bleibt unverändert?** Ein expliziter Pfad hat Vorrang.

**Risiko:** Ein Tippfehler durch Weglassen kann nun auf ein leeres
Default-Verzeichnis zeigen.

**Absicherung:** Schema-Test und PluginManager-Fallback.

**Review-Hinweis:** `schema/solution.json`, generiertes `solution.py` und
`plugins/manager.py`.

### Entity Rename

**Was war vorher?** Basiseinträge konnten erstellt, geändert und verschoben,
aber nicht sauber innerhalb ihrer gemeinsamen JSON-Datei umbenannt werden.

**Was ändert sich?** `POST /entities/rename` benennt Base Entities und
Property Values um und merkt sich den alten Container-Schlüssel bis zum Save.

**Warum brauchen wir das?** Ein Rename soll den vorhandenen Eintrag ersetzen,
nicht einen zweiten Eintrag erzeugen.

**Einfaches Beispiel:** `dataTypes/Text` wird zu `dataTypes/String`, während
`Number` in derselben Datei unverändert bleibt.

**Was bleibt unverändert?** Model Entities und Ordner werden weiterhin über
`/entities/move` umbenannt.

**Risiko:** Property Values haben einen zusammengesetzten Schlüssel aus
Property und Name.

**Absicherung:** Kollisionsprüfung, Locator-Regeln und Persistenztest mit
gemeinsamer JSON-Datei.

**Review-Hinweis:** `Model.rename_entity()` und `EntityFileRef.update()`.

### Function Source Read, Write, Delete und Rename

**Was war vorher?** Function-Dateien waren über die Main-API nicht
bearbeitbar.

**Was ändert sich?** Vier HTTP-Operationen lesen, schreiben, löschen und
benennen Dateien relativ zu einer Model Entity um.

**Warum brauchen wir das?** Neon kann Function-Code bearbeiten, ohne direkten
Dateisystemzugriff zu benötigen.

**Einfaches Beispiel:** `helpers/normalize.sql` wird für
`modelEntities/core/Customer` gespeichert.

**Was bleibt unverändert?** Die Model-JSON-Datei wird durch das Schreiben einer
Function-Datei nicht verändert.

**Risiko:** Teilweise geschriebene Dateien bei Prozessabbruch.

**Absicherung:** Schreiben erfolgt über eine temporäre Datei und atomisches
`replace`.

**Review-Hinweis:** `function_sources.py` und `/model/function/*`.

### Sichere Function-Pfade

**Was war vorher?** Die Beta-Prüfung blockierte `..`, aber nicht alle
Windows-, Drive- und Symlink-Fälle.

**Was ändert sich?** Sowohl syntaktische Pfade als auch vollständig aufgelöste
Zielpfade müssen innerhalb des Entity-Roots liegen.

**Warum brauchen wir das?** Die API darf keine beliebigen Dateien auf dem
Rechner lesen oder überschreiben.

**Einfaches Beispiel:** `C:\secret.txt`, `../secret.txt` und ein Symlink nach
außerhalb werden abgelehnt.

**Was bleibt unverändert?** Normale relative Unterordner bleiben erlaubt.

**Risiko:** Plattformunterschiede bei Symlinks und Reparse Points.

**Absicherung:** Tests für Posix-, Windows-, UNC-, Traversal-, Leersegment- und
Symlink-Pfade.

**Review-Hinweis:** `normalize_source_path()` und `_require_contained()`.

### Atomare Entity- und Function-Moves

**Was war vorher?** Beta änderte zuerst das In-Memory-Model und bewegte danach
den Function-Ordner. Ein Dateisystemfehler hinterließ inkonsistenten Zustand.

**Was ändert sich?** Bei Model Entities wird der Function-Ordner vorab geprüft
und bewegt. Schlägt das anschließende Model-Move fehl, wird der Ordner
zurückbewegt.

**Warum brauchen wir das?** Model und Function-Dateien sollen denselben Locator
verwenden.

**Einfaches Beispiel:** `raw/Customer` nach `core/Customer`; bei Zielkonflikt
bleibt beides unter `raw`.

**Was bleibt unverändert?** Ohne vorhandenen Function-Ordner läuft der normale
Model-Move.

**Risiko:** Ein Prozessabbruch zwischen Betriebssystem-Rename und Model-Move
kann nicht durch Python-Rollback behandelt werden.

**Absicherung:** Vorprüfung, HTTP 409 bei Zielkonflikt und expliziter
Rollback-Test.

**Review-Hinweis:** `move_entity_directory()` und Entity-Move-Route.

### Source-Kompatibilitätsrouten

**Was war vorher?** Beta verwendete SQL-förmige `/schemas`- und `/tables`-
Routen; Main verwendet die generische `/locations`-API.

**Was ändert sich?** Die alten Pfade existieren als Adapter und rufen die
generischen Plugin-Methoden auf.

**Warum brauchen wir das?** Bestehende Clients können weiterarbeiten, ohne die
neuere Plugin-Architektur zurückzubauen.

**Einfaches Beispiel:** `schemas/dbo/tables/Customer/preview` wird intern zu
Preview für `dbo.Customer`.

**Was bleibt unverändert?** `/locations` bleibt die kanonische API.

**Risiko:** Der Punkt-Separator ist ein SQL-Kompatibilitätsformat und nicht für
jeden zukünftigen Connector geeignet.

**Absicherung:** Adaptertests vergleichen Metadata und Preview mit den
kanonischen Funktionen.

**Review-Hinweis:** Kompatibilitätsabschnitt in `api/routes/sources.py`.

### Generierung der Model-Klassen

**Was war vorher?** Beta enthielt manuell veränderten Generated Code, der nicht
vollständig zum Model-Repository passte.

**Was ändert sich?** Das Generator-Submodule zeigt auf den Model-Port; alle
Model-Klassen werden mit `uv build` reproduzierbar erzeugt.

**Warum brauchen wir das?** Schema und Python-Klassen dürfen nicht
auseinanderlaufen.

**Einfaches Beispiel:** `SourceOverride` erscheint nach `uv build` automatisch
in `src/datam8_model/data_source.py`.

**Was bleibt unverändert?** Die generierten Klassen bleiben Bestandteil des
Generator-Packages.

**Risiko:** Änderungen am Codegen-Tool können große, unbeabsichtigte Diffs
erzeugen.

**Absicherung:** Nur vier fachlich betroffene generierte Module ändern sich;
Ruff, Pyright und Tests laufen danach.

**Review-Hinweis:** Submodule-Pointer, `hatch_build_datamodel.py` und Template.

### Baseline- und Pyright-Korrekturen

**Was war vorher?** Main hatte 26 Typfehler, unter anderem bei Alias-Feldern,
Generic-Repositories, optionalem Pluginpfad, SQL-Match und Keyring-Import.

**Was ändert sich?** Diese Fehler sind in einem separaten Commit ohne
beabsichtigte API-Änderung behoben.

**Warum brauchen wir das?** Pyright ist ein verpflichtendes CI-Gate.

**Einfaches Beispiel:** Intern wird `output_path=` statt des JSON-Alias
`outputPath=` an den Pydantic-Konstruktor übergeben; die Response bleibt
`outputPath`.

**Was bleibt unverändert?** JSON-Aliase und öffentliche Payloads bleiben
gleich.

**Risiko:** Typ-Casts könnten echte Modellierungsprobleme verdecken.

**Absicherung:** Die Casts sind auf bekannte Generic-Invarianz begrenzt; volle
Testsuite und Pyright laufen.

**Review-Hinweis:** Commit `1598f72` separat prüfen.

## Port-Matrix Generator

| Beta Commit | Status | Begründung |
|---|---|---|
| `ff840cb` | Portiert | UI-String-Enums über Model und Generated Code |
| `0441130` | Portiert | `previewData` inklusive Capability Enforcement |
| `8ec5cb2` | Portiert und korrigiert | Externe Relationships ohne Integer-`min_length`-Fehler |
| `86c933a` | Bereits in Main | Reiner Ruff-Fix, neuer Stand ist Ruff-clean |
| `05bf08f` | Portiert und korrigiert | Entity Rename plus robuste Container-Persistenz |
| `9429fe6` | Semantisch aufgeteilt | Relevante API-, Model- und Baseline-Teile einzeln portiert |
| `a6d4941` | Nicht übernommen | Kein direkter YAML-Import im Generator; PyYAML ist bereits transitive Lock-Abhängigkeit |
| `4cb72ee` | Portiert | Source Override aus dem Schema statt manuellem Generated Code |
| `dcf160c` | Portiert | Source- und Field-Beschreibungen/Properties |
| `dc42a7c` | Bereits in Main | Zone-Auflösung unterstützt Name und Local Folder Name |
| `643f2d2` | Bereits in Main | Historischer Merge aus Main, kein eigener Feature-Inhalt |
| `8eced56` | Ersetzt | Aktuelle SecretResolver-Implementierung plus öffentlicher Keyring-Fehlertyp |
| `75e8ecd` | Bereits in Main | Property-Listen werden vor Vererbung kopiert |
| `baafb7a` | Bereits in Main | Aktuelle Wrapper-Update-Logik |
| `f1f5736` | Durch Main ersetzt | Aktueller PluginManager und generische Source-Schnittstelle |
| `a8c04cd` | Bereits in Main | Code-Templates laufen ohne HTML-Autoescape |
| `3523712` | Durch Main ersetzt | Unspezifischer historischer Fix ist im neuen Unterbau enthalten |
| `fc82a81` | Durch Main ersetzt | Alte Codename-Behandlung ist nicht mehr vorhanden |
| `c62e64d` | Durch Main ersetzt | Aktueller PluginManager |
| `027f0bf` | Bereits in Main | Neuer Stand besteht Ruff und Pyright |
| `c3b99c8` | Durch Main ersetzt | Aktuelle Solution-Erstellung und API-Struktur |
| `cde47c2` | Durch Main ersetzt | Aktuelle `add_entity`-Implementierung |
| `a5dd04f` | Durch Main ersetzt | Aktuelle Secrets- und SQL-Server-Implementierung |
| `d251f6f` | Durch Main ersetzt | Unspezifischer historischer Fix |
| `7a34b98` | Durch Main ersetzt | Aktuelle Base-Entity-Repositories |
| `2651304` | Durch Main ersetzt | Aktuelle Folder- und Locator-Verarbeitung |
| `9d26601` | Teilweise portiert | Move-Payload korrigiert; Sidecar-Move sicher neu implementiert |
| `753b08d` | Durch Main ersetzt | Unspezifischer historischer Fix |
| `40e0f0a` | Nicht übernommen | Historische Dokumentation war nicht mehr mit den Main-Routen konsistent |
| `65aed6c` | Portiert und gehärtet | Function-Endpunkte mit sicherem Dateisystem-Service |
| `dd8df5c` | Bereits in Main | Neuer Stand besteht Ruff |
| `7859250` | Durch Main ersetzt | Aktuelle Solution-Funktionen |
| `94d7935` | Durch Main ersetzt | Unspezifische ältere Korrekturen |
| `5844456` | Durch Main ersetzt | Aktuelle Delete-/Move-Logik; Function-Sidecar separat portiert |

## Bewusst nicht übernommen

- Keine globale Exception-Antwort mit `str(exc)` und Exception-Typ.
- Keine `coming soon`-Import-Endpunkte.
- Keine Wiederherstellung von `list_schemas` und `list_tables` im Plugin-Base.
- Kein untypisiertes `SourceField.relationships`.
- Keine manuellen Änderungen an generierten Model-Dateien.
- Keine alten, hart codierten Solution-Defaults aus Beta.
- Keine direkte PyYAML-Abhängigkeit ohne Importstelle.
- Keine veralteten Backend-Dokumente mit nicht vorhandenen Endpunkten.

## Bekannte Grenzen

- Der Symlink-Test wird auf Windows ohne Developer Mode oder entsprechendes
  Recht übersprungen.
- Der kompatible Sample-Branch enthält die von einem bestehenden Test
  erwartete Property Value `jobs/sales_weekly` nicht.
- Der alte offizielle `feature/v2`-Sample-Commit ist mit aktuellem Main
  grundsätzlich inkompatibel und darf nicht als Port-Regression gewertet
  werden.
- Neon `feature/v2-beta` sendet für Function-Dateien teilweise noch
  `{relPath, source, entityName}`. Der kanonische Backend-Vertrag verwendet
  `{locator, source, content}`; Neon wurde in diesem Port nicht verändert.
- Der transaktionale Function-Verzeichnis-Move gilt für einzelne Model
  Entities. Ordner-Subtree-Moves bleiben Aufgabe der bestehenden Model-Logik.

## Lokale Befehle

```powershell
cd C:\Users\f.kayser\Projects\ORAYLIS\Automation\Repos\datam8-model
git switch feature/v2-beta-port
uv run --with jsonschema python validate-schema.py
uv run --with jsonschema python -m unittest discover -s tests -v

cd C:\Users\f.kayser\Projects\ORAYLIS\Automation\Repos\datam8-generator
git switch feature/v2-beta-port
git submodule update --init
uv sync --all-extras
uv build
uv tool run ruff check src
uv tool run pyright src

$env:DATAM8_SOLUTION_PATH='C:\Users\f.kayser\AppData\Local\Temp\datam8-sample-v2-beta-port-test\ORAYLISDatabricksSample.dm8s'
uv run pytest -q
```

Output neu erzeugen:

```powershell
uv run datam8 generate databricks `
  -s C:\path\to\ORAYLISDatabricksSample.dm8s `
  --clean-output
```

Branch-Diffs:

```powershell
git diff --stat origin/main...feature/v2-beta-port
git log --oneline origin/main..feature/v2-beta-port
```

## Was morgen noch getan werden muss

1. Zuerst `datam8-model/feature/v2-beta-port` reviewen.
2. Model-Branch pushen, damit Commit `fcce955` remote erreichbar ist.
3. Generator-Submodule nach dem Push auf exakt denselben Remote-Commit prüfen.
4. Generator-Branch pushen.
5. Model-PR mit dem vorbereiteten Text eröffnen.
6. Generator-PR als abhängig vom Model-PR eröffnen.
7. Fehlende Sample-Fixture `jobs/sales_weekly` separat klären.
8. Optional Developer Mode aktivieren und Symlink-Security-Test erneut laufen lassen.
9. Neon-Function-Bridge auf den dokumentierten Locator-Payload umstellen oder die Integration separat terminieren.
10. Erst nach vollständiger Review über einen Merge nach `main` entscheiden.
