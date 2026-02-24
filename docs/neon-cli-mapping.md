# Neon CLI Mapping and API/CLI Parity

Stand: 2026-02-12

Diese Datei ist die zusammengefuehrte Sicht auf:

- Neon Runtime-Nutzung der Generator-Funktionen
- API/CLI-Paritaet im Generator

## Top-Level Mapping (Neon Runtime)

| CLI-Gruppe | Was im Frontend damit gemacht wird (non-tech) | Wie Neon es nutzt | Referenzen |
|---|---|---|---|
| `solution` | Loesung oeffnen, pruefen, komplett laden, neues Projekt anlegen | HTTP: `/solution/inspect`, `/solution/full`, `/solution/new-project` | `apps/web/src/features/solution/solutionLoader.ts:44`, `apps/web/src/features/solution/solutionLoader.ts:124`, `apps/web/src/app/NewProjectDialog.tsx:40` |
| `base` | Basisdateien (Stammdaten) speichern | HTTP: `/base/entities` | `apps/web/src/app/AppShell.tsx:788` |
| `model` | Entitaeten speichern/verschieben/umbenennen, Funktionscode bearbeiten | HTTP: `/model/entities`, `/model/entities/move`, `/model/folder/rename`, `/model/function/source`, `/model/function/rename` | `apps/web/src/app/AppShell.tsx:580`, `apps/web/src/app/AppShell.tsx:904`, `apps/web/src/app/AppShell.tsx:622`, `apps/web/src/features/model/components/workspace/hooks/useEntityState.ts:561`, `apps/web/src/features/model/components/workspace/entity-editor/EntityTransformationsEditor.tsx:76` |
| `script` | Keine eigene sichtbare UI-Funktion (separate Script-Endpunkte) | Kein aktiver Runtime-Treffer fuer `/script/*`; script-nahe Arbeit laeuft ueber `/model/function/*` | `apps/web/src/features/model/components/workspace/hooks/useEntityState.ts:561` |
| `index` | Nach Aenderungen den Index neu aufbauen | HTTP: `/index/regenerate` | `apps/web/src/app/AppShell.tsx:591` |
| `refactor` | Property-Refactor ausfuehren | HTTP: `/refactor/properties` | `apps/web/src/app/AppShell.tsx:764` |
| `search` | Aktuell keine aktive Such-UI gegen Backend-Endpunkte | Keine Runtime-Treffer fuer `/search/entities` oder `/search/text` | `src/datam8/api/routes/api_workspace.py:690`, `src/datam8/api/routes/api_workspace.py:697` |
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

## API/CLI Parity Matrix

Shared sources of truth:

- `src/datam8/core/workspace_service.py` fuer Workspace-Mutationen/Listings/Index
- `src/datam8/generate.py` fuer synchrone Generation
- `src/datam8/factory.py` fuer Full-Model-Validierung (Parse + Resolve)

| Domain | Use case | HTTP API | CLI | Shared source |
|---|---|---|---|---|
| Solution | Detect solution version | `GET /solution/inspect` | `datam8 solution inspect` | `solution_index.detect_solution_version` |
| Solution | Read resolved solution metadata | `GET /solution/info` | `datam8 solution info` | `workspace_io.read_solution` |
| Solution | Read full workspace snapshot | `GET /solution/full` | `datam8 solution full` | `workspace_service.get_solution_full_snapshot` |
| Solution | Validate solution metadata | `POST /solution/validate` | `datam8 solution validate` | `workspace_io.read_solution` |
| Validate | Validate full model parse/resolve | `POST /validate` | `datam8 validate` | `factory.validate_solution_model` |
| Solution | Create new project | `POST /solution/new-project` | `datam8 solution new-project` | `workspace_io.create_new_project` |
| Generate | Synchronous generation | `POST /generate` | `datam8 generate` | `generate.run_generation` |
| Model | List entities | `GET /model/entities` | `datam8 model list` | `workspace_service.list_model_entities` |
| Model | Read entity by selector | `GET /model/entity` | `datam8 model get` | selector resolution + `workspace_io.read_workspace_json` |
| Model | Create entity | `POST /model/entity/create` | `datam8 model create` | `workspace_service.create_model_entity` |
| Model | Save entity | `POST /model/entities` | `datam8 model save` / `set` / `patch` / `edit` | `workspace_service.save_model_entity` |
| Model | Validate entity object | `POST /model/entity/validate` | `datam8 model validate` | selector resolution + JSON object check |
| Model | Duplicate entity | `POST /model/entity/duplicate` | `datam8 model duplicate` | `workspace_service.duplicate_model_entity` |
| Model | Delete entity | `DELETE /model/entities` | `datam8 model delete` | `workspace_service.delete_model_entity` |
| Model | Move entity | `POST /model/entities/move` | `datam8 model move` | `workspace_service.move_model_entity` |
| Model | Rename folder + refresh index | `POST /model/folder/rename` | `datam8 model folder-rename` | `workspace_service.rename_model_folder` |
| Folder metadata | Read folder metadata | `GET /model/folder-metadata` | `datam8 model folder-metadata get` | `workspace_service.read_folder_metadata` |
| Folder metadata | Save folder metadata | `POST /model/folder-metadata` | `datam8 model folder-metadata save` | `workspace_service.save_folder_metadata` |
| Folder metadata | Delete folder metadata | `DELETE /model/folder-metadata` | `datam8 model folder-metadata delete` | `workspace_service.delete_folder_metadata` |
| Base | List entities | `GET /base/entities` | `datam8 base list` | `workspace_service.list_base_entities` |
| Base | Read entity | `GET /base/entity` | `datam8 base get` | `workspace_io.read_workspace_json` |
| Base | Save entity | `POST /base/entities` | `datam8 base save` / `set` / `patch` / `edit` | `workspace_service.save_base_entity` |
| Base | Delete entity | `DELETE /base/entities` | `datam8 base delete` | `workspace_service.delete_base_entity` |
| Index | Regenerate | `POST /index/regenerate` | `datam8 index regenerate` | `workspace_service.regenerate_index` |
| Index | Show | `GET /index/show` | `datam8 index show` | `solution_index.read_index` |
| Index | Validate | `GET /index/validate` | `datam8 index validate` | `solution_index.validate_index` |
| Script | List function sources | `GET /script/list` | `datam8 script list` | `workspace_io.list_function_sources` |
| Script | Read function source | `GET /model/function/source` | `datam8 script get` | `workspace_io.read_function_source` |
| Script | Save function source | `POST /model/function/source` | `datam8 script save` | `workspace_io.write_function_source` |
| Script | Rename function source | `POST /model/function/rename` | `datam8 script rename` | `workspace_io.rename_function_source` |
| Script | Delete function source | `DELETE /script/delete` | `datam8 script delete` | `workspace_io.delete_function_source` |
| Refactor | Property refactor | `POST /refactor/properties` | `datam8 refactor properties` | `workspace_io.refactor_properties` |
| Refactor | Key refactor | `POST /refactor/keys` | `datam8 refactor keys` | `refactor.refactor_keys` |
| Refactor | Value refactor | `POST /refactor/values` | `datam8 refactor values` | `refactor.refactor_values` |
| Refactor | Entity-id refactor | `POST /refactor/entity-id` | `datam8 refactor entity-id` | `refactor.refactor_entity_id` |
| Search | Search entities | `GET /search/entities` | `datam8 search entities` | `search.search_entities` |
| Search | Search text | `GET /search/text` | `datam8 search text` | `search.search_text` |
| Filesystem | List directory | `GET /fs/list` | `datam8 fs list` | `workspace_io.list_directory` |
| Connector | List connectors | `GET /connectors` | `datam8 connector list` | `plugin_host.discover_connectors` |
| Connector | Read connector UI schema | `GET /connectors/{connectorId}/ui-schema` | `datam8 connector ui-schema` | `plugin_host.load_ui_schema` |
| Connector | Validate connector connection | `POST /connectors/{connectorId}/validate-connection` | `datam8 connector validate-connection` | `plugin_host.validate_connection` |
| Connector | Test datasource connectivity | `POST /datasources/{dataSourceId}/test` | `datam8 connector test` | `connectors.resolve.resolve_and_validate` + connector `test_connection` |
| Connector/Datasource | Browse datasource tables | `POST /datasources/{dataSourceId}/list-tables` | `datam8 connector browse` / `datam8 datasource list-tables` | `connectors.resolve.resolve_and_validate` + connector `list_tables` |
| Connector/Datasource | Fetch datasource table metadata | `POST /datasources/{dataSourceId}/table-metadata` | `datam8 connector fetch-metadata` / `datam8 datasource table-metadata` | `connectors.resolve.resolve_and_validate` + connector `get_table_metadata` |
| Datasource | HTTP virtual table metadata | `POST /http/datasources/{dataSourceId}/virtual-table-metadata` | `datam8 datasource virtual-table-metadata` | connector metadata resolution |
| Datasource | Usages | `GET /datasources/{dataSourceId}/usages` | `datam8 datasource usages` | `schema_refresh.find_data_source_usages` |
| Datasource | Refresh preview | `POST /datasources/{dataSourceId}/refresh-external-schemas/preview` | `datam8 datasource refresh-preview` | `schema_refresh.preview_schema_changes` |
| Datasource | Refresh apply | `POST /datasources/{dataSourceId}/refresh-external-schemas/apply` | `datam8 datasource refresh-apply` | `schema_refresh.apply_schema_changes` |
| Plugin | List/reload/install/enable/disable/uninstall | `GET /plugins`, `POST /plugins/reload`, `POST /plugins/install`, `POST /plugins/enable`, `POST /plugins/disable`, `POST /plugins/uninstall` | `datam8 plugin list/reload/install/enable/disable/uninstall` | `plugin_manager.*` |
| Plugin | Plugin info | `GET /plugins/{pluginId}/info` | `datam8 plugin info` | plugin state lookup |
| Plugin | Plugin verify | `POST /plugins/{pluginId}/verify`, `POST /plugins/verify` | `datam8 plugin verify` | installed-plugin or ZIP verification |
| Secret | Availability | `GET /secrets/available` | `datam8 secret available` | `secrets.is_keyring_available` |
| Secret | List keys | `GET /secrets/runtime/list` | `datam8 secret list` | `secrets.list_runtime_secret_keys` |
| Secret | Secret refs | `GET /secrets/runtime` | `datam8 secret refs` | `secrets.runtime_secret_ref` |
| Secret | Get value | `GET /secrets/runtime/key` | `datam8 secret get` | `secrets.get_runtime_secret` |
| Secret | Set value | `PUT /secrets/runtime` | `datam8 secret set` | `secrets.set_runtime_secret` |
| Secret | Delete key | `DELETE /secrets/runtime/key` | `datam8 secret delete` | `secrets.delete_runtime_secret` |
| Secret | Clear datasource secrets | `DELETE /secrets/runtime` | `datam8 secret clear` | `secrets.delete_runtime_secret` |

## CLI functionality currently not used by Neon runtime

Folgende CLI-Funktionen sind im Generator vorhanden, aber laut aktueller Neon-Runtime-Verdrahtung nicht aktiv genutzt:

- `datam8 validate` (eigener Full-Model-Flow im Frontend nicht verdrahtet)
- `datam8 search entities`, `datam8 search text`
- `datam8 index show`, `datam8 index validate`
- `datam8 refactor keys`, `datam8 refactor values`, `datam8 refactor entity-id`
- `datam8 plugin enable`, `datam8 plugin disable`, `datam8 plugin info`, `datam8 plugin verify`
- `datam8 secret available`, `datam8 secret list`, `datam8 secret refs`, `datam8 secret get`, `datam8 secret clear`
- `datam8 script list/get/save/rename/delete` als eigene Gruppe (UI nutzt primaer `/model/function/*`)
- `datam8 connector test`, `datam8 connector browse`, `datam8 connector fetch-metadata` als direkte Connector-Flows

## Verwandte Doku

- `docs/backend-contract.md` (kanonischer HTTP-Vertrag zwischen Neon und Generator)
