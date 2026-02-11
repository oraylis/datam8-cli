# Neon CLI Mapping (Top-Level Commands)

Stand: 2026-02-11

Diese Datei beschreibt, wie die Top-Level-CLI-Gruppen aus `datam8-generator` im `datam8-neon` Frontend genutzt werden.

## Mapping-Liste

| CLI-Gruppe | Was im Frontend damit gemacht wird (non-tech) | Wie Neon es nutzt | Referenzen |
|---|---|---|---|
| `solution` | Loesung oeffnen, pruefen, komplett laden, neues Projekt anlegen | HTTP: `/solution/inspect`, `/solution/full`, `/solution/new-project` | `apps/web/src/features/solution/solutionLoader.ts:44`, `apps/web/src/features/solution/solutionLoader.ts:124`, `apps/web/src/app/NewProjectDialog.tsx:40` |
| `base` | Basisdateien (Stammdaten) speichern | HTTP: `/base/entities` | `apps/web/src/app/AppShell.tsx:788` |
| `model` | Entitaeten speichern/verschieben/umbenennen, Funktionscode bearbeiten | HTTP: `/model/entities`, `/model/entities/move`, `/model/folder/rename`, `/model/function/source`, `/model/function/rename` | `apps/web/src/app/AppShell.tsx:580`, `apps/web/src/app/AppShell.tsx:904`, `apps/web/src/app/AppShell.tsx:622`, `apps/web/src/features/model/components/workspace/hooks/useEntityState.ts:561`, `apps/web/src/features/model/components/workspace/entity-editor/EntityTransformationsEditor.tsx:76` |
| `script` | Keine eigene sichtbare UI-Funktion (separate Script-Endpunkte) | Kein aktiver Runtime-Treffer fuer `/script/*`; script-nahe Arbeit laeuft ueber `/model/function/*` | `apps/web/src/features/model/components/workspace/hooks/useEntityState.ts:561` |
| `index` | Nach Aenderungen den Index neu aufbauen | HTTP: `/index/regenerate` | `apps/web/src/app/AppShell.tsx:591` |
| `refactor` | Property-Refactor ausfuehren | HTTP: `/refactor/properties` | `apps/web/src/app/AppShell.tsx:764` |
| `search` | Aktuell keine aktive Such-UI gegen Backend-Endpunkte | Keine Runtime-Treffer fuer `/search/entities` oder `/search/text` | `src/datam8/api/routes/api_workspace.py:479`, `src/datam8/api/routes/api_workspace.py:486` |
| `connector` | Connector-Liste anzeigen, Connector-Form laden, Verbindung testen | HTTP: `/connectors`, `/connectors/{id}/ui-schema`, `/connectors/{id}/validate-connection` | `apps/web/src/shared/connectors/connectorCatalog.ts:37`, `apps/web/src/features/model/components/workspace/base-editor/ConnectorUiSchemaForm.tsx:62`, `apps/web/src/features/model/components/workspace/base-editor/ConnectorUiSchemaForm.tsx:69` |
| `plugin` | Plugins anzeigen, installieren, reloaden, deinstallieren | HTTP: `/plugins`, `/plugins/install`, `/plugins/reload`, `/plugins/uninstall` | `apps/web/src/shared/connectors/ConnectorPickerDialog.tsx:21`, `apps/web/src/shared/connectors/ConnectorPickerDialog.tsx:64`, `apps/web/src/shared/connectors/ConnectorPickerDialog.tsx:148`, `apps/web/src/shared/connectors/ConnectorPickerDialog.tsx:230` |
| `secret` | Laufzeit-Secrets (z. B. Passwoerter/Tokens) schreiben/loeschen | HTTP: `/secrets/runtime`, `/secrets/runtime/key` | `apps/web/src/features/model/components/workspace/base-editor/ConnectorUiSchemaForm.tsx:80`, `apps/web/src/features/model/components/workspace/base-editor/ConnectorUiSchemaForm.tsx:92` |
| `datasource` | Tabellen/Metadaten lesen, externe Schema-Aenderungen vorschauen/anwenden | HTTP: `/datasources/*`, `/http/datasources/*` | `apps/web/src/features/model/components/wizard/SourceRow.tsx:75`, `apps/web/src/features/model/components/wizard/SourceRow.tsx:103`, `apps/web/src/features/model/components/wizard/SourceRow.tsx:138`, `apps/web/src/features/model/components/workspace/base-editor/RefreshSchemasDialog.tsx:164`, `apps/web/src/features/model/components/workspace/base-editor/RefreshSchemasDialog.tsx:216`, `apps/web/src/features/model/components/workspace/base-editor/RefreshSchemasDialog.tsx:472` |
| `config` | UI ermittelt den Laufmodus (server/electron/browser) | HTTP: `/config` | `apps/web/src/config.ts:45` |
| `migration` | V1->V2 Migration per Wizard | HTTP: `/migration/v1-to-v2` | `apps/web/src/features/migration/components/MigrateSolutionV1Wizard.tsx:98` |
| `fs` | Dateibrowser im Loesungsdialog | HTTP: `/fs/list` | `apps/web/src/features/fs/FileSystemContext.tsx:24` |
| `generate` | Generator im UI starten | HTTP: `/generate` | `apps/web/src/features/generator/GeneratorContext.tsx:95` |
| `validate` | Aktuell keine aktive Frontend-Nutzung als eigener Flow | Kein Treffer fuer `datam8 validate` und kein eigener `/validate`-Flow im Neon Runtime-Code | `src/datam8/cmd/validate.py:34` |
| `serve` | Backend-Prozess beim Start der Desktop-App hochfahren | Direkter CLI-Prozessstart: `python -m datam8 serve ...` | `apps/desktop/src/main.ts:354`, `scripts/ci-gates.mjs:204` |

## Hinweise / Nicht aktiv verdrahtete Teilbereiche

- `plugin`: `enable`/`disable` sind als Backend-Endpunkte vorhanden, aber aktuell nicht sichtbar im Runtime-UI verdrahtet.
- `index`: `show` und `validate` sind vorhanden, im Runtime-UI aber nicht genutzt.
- `refactor`: `keys`, `values`, `entity-id` sind vorhanden, im Runtime-UI aber nicht genutzt.
- `search`: Endpunkte vorhanden, aber keine aktive Runtime-UI-Nutzung.
- `script`: eigene `/script/*` Endpunkte vorhanden, Runtime-UI nutzt stattdessen primar `/model/function/*`.

## Verwandte Doku

- `docs/backend-contract.md` (kanonischer HTTP-Vertrag zwischen Neon und Generator)
