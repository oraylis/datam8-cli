from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from datam8.core.connectors.plugin_manager import (
    default_plugin_dir,
    install_git_url,
    install_zip,
    reload as reload_plugins,
    set_enabled,
    uninstall,
)
from datam8.core.connectors.plugin_host import get_connector, load_ui_schema, validate_connection
from datam8.core.connectors.resolve import resolve_and_validate
from datam8.core.duration import parse_duration_seconds
from datam8.core.errors import Datam8NotImplementedError, Datam8ValidationError
from datam8.core.indexing import read_index, validate_index
from datam8.core.lock import SolutionLock
from datam8.core.migration_v1_to_v2 import migrate_solution_v1_to_v2
from datam8.core.refactor import refactor_entity_id, refactor_keys, refactor_values
from datam8.core.schema_refresh import (
    UsageRef,
    apply_schema_changes,
    find_data_source_usages,
    preview_schema_changes,
)
from datam8.core.search import search_entities, search_text
from datam8.core.secrets import (
    delete_runtime_secret,
    get_runtime_secrets_map,
    is_keyring_available,
    list_runtime_secret_keys,
    set_runtime_secret,
    runtime_secret_ref,
)
from datam8.core.solution_files import detect_solution_version
from datam8.core.workspace_io import (
    create_new_project,
    delete_base_entity,
    delete_function_source,
    delete_model_entity,
    list_base_entities,
    list_directory,
    list_function_sources,
    list_model_entities,
    move_model_entity,
    read_function_source,
    read_solution,
    refactor_properties,
    regenerate_index,
    rename_folder,
    rename_function_source,
    write_base_entity,
    write_function_source,
    write_model_entity,
)

router = APIRouter()

PLUGIN_DIR = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
_plugin_state: dict[str, Any] = {"pluginDir": str(PLUGIN_DIR), "plugins": [], "errors": {}}
_plugins_loaded: bool = False


def _ensure_plugins_loaded() -> None:
    global _plugin_state, _plugins_loaded
    if _plugins_loaded:
        return
    _plugin_state = reload_plugins(PLUGIN_DIR)
    _plugins_loaded = True

def _lock_timeout_seconds(body: Any) -> float:
    try:
        v = body.get("lockTimeout")
        if isinstance(v, str) and v.strip():
            return parse_duration_seconds(v)
    except Exception:
        pass
    return parse_duration_seconds("10s")


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/config")
async def config() -> dict[str, Any]:
    # Minimal shape used by the web UI.
    return {"mode": os.environ.get("DATAM8_MODE") or "server"}


@router.get("/api/solution/inspect")
async def solution_inspect(path: str = Query(...)) -> dict[str, str]:
    return {"version": detect_solution_version(path)}


class MigrateV1ToV2Body(BaseModel):
    sourceSolutionPath: str
    targetDir: str
    options: dict[str, Any] | None = None


@router.post("/api/migration/v1-to-v2")
async def migration_v1_to_v2(body: MigrateV1ToV2Body) -> dict[str, Any]:
    args: dict[str, Any] = {"sourceSolutionPath": body.sourceSolutionPath, "targetDir": body.targetDir}
    if body.options is not None:
        args["options"] = body.options
    return migrate_solution_v1_to_v2(args)


@router.get("/api/solution")
async def solution(path: str | None = Query(None)) -> dict[str, Any]:
    _resolved, sol = read_solution(path)
    return {"solution": sol.model_dump(), "resolvedPaths": {"base": sol.basePath, "model": sol.modelPath}}


@router.get("/api/solution/full")
async def solution_full(path: str | None = Query(None)) -> dict[str, Any]:
    _resolved, sol = read_solution(path)
    base_entities = [e.__dict__ for e in list_base_entities(path)]
    model_entities = [e.__dict__ for e in list_model_entities(path)]
    return {"solution": sol.model_dump(), "baseEntities": base_entities, "modelEntities": model_entities}


class NewProjectBody(BaseModel):
    solutionName: str
    projectRoot: str
    basePath: str | None = None
    modelPath: str | None = None
    target: str


@router.post("/api/solution/new-project")
async def solution_new_project(body: NewProjectBody) -> dict[str, str]:
    solution_path = create_new_project(
        solution_name=body.solutionName,
        project_root=body.projectRoot,
        base_path=body.basePath,
        model_path=body.modelPath,
        target=body.target,
    )
    return {"solutionPath": solution_path}


@router.get("/api/model/entities")
async def model_entities(path: str | None = Query(None)) -> dict[str, Any]:
    entities = [e.__dict__ for e in list_model_entities(path)]
    return {"count": len(entities), "entities": entities}


class SaveEntityBody(BaseModel):
    relPath: str
    content: Any
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/api/model/entities")
async def model_entities_save(body: SaveEntityBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        abs_path = write_model_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = write_model_entity(body.relPath, body.content, body.solutionPath)
    return {"message": "saved", "absPath": abs_path}


class DeleteEntityBody(BaseModel):
    relPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.delete("/api/model/entities")
async def model_entities_delete(body: DeleteEntityBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        abs_path = delete_model_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = delete_model_entity(body.relPath, body.solutionPath)
    return {"message": "deleted", "absPath": abs_path}


class MoveEntityBody(BaseModel):
    fromRelPath: str
    toRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/api/model/entities/move")
async def model_entities_move(body: MoveEntityBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        result = move_model_entity(body.fromRelPath, body.toRelPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = move_model_entity(body.fromRelPath, body.toRelPath, body.solutionPath)
    return {"message": "moved", **result}


class RenameFolderBody(BaseModel):
    fromFolderRelPath: str
    toFolderRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/api/model/folder/rename")
async def model_folder_rename(body: RenameFolderBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        result = rename_folder(body.fromFolderRelPath, body.toFolderRelPath, body.solutionPath)
        entities = [e.__dict__ for e in list_model_entities(body.solutionPath)]
        regenerate_index(body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = rename_folder(body.fromFolderRelPath, body.toFolderRelPath, body.solutionPath)
            entities = [e.__dict__ for e in list_model_entities(body.solutionPath)]
            regenerate_index(body.solutionPath)
    return {"message": "renamed", **result, "entities": entities}


class RefactorPropertiesBody(BaseModel):
    solutionPath: str | None = None
    propertyRenames: list[dict[str, str]] = Field(default_factory=list)
    valueRenames: list[dict[str, str]] = Field(default_factory=list)
    deletedProperties: list[str] = Field(default_factory=list)
    deletedValues: list[dict[str, str]] = Field(default_factory=list)
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/api/refactor/properties")
async def refactor_properties_route(body: RefactorPropertiesBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        result = refactor_properties(
            solution_path=body.solutionPath,
            property_renames=body.propertyRenames,
            value_renames=body.valueRenames,
            deleted_properties=body.deletedProperties,
            deleted_values=body.deletedValues,
        )
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = refactor_properties(
                solution_path=body.solutionPath,
                property_renames=body.propertyRenames,
                value_renames=body.valueRenames,
                deleted_properties=body.deletedProperties,
                deleted_values=body.deletedValues,
            )
    return {"message": "refactored", **result}


@router.post("/api/index/regenerate")
async def index_regenerate(body: dict[str, Any]) -> dict[str, Any]:
    solution_path = body.get("solutionPath")
    resolved, _sol = read_solution(solution_path)
    if body.get("noLock"):
        index = regenerate_index(solution_path)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body)):
            index = regenerate_index(solution_path)
    return {"message": "index regenerated", "index": index}


@router.get("/api/index/show")
async def index_show(path: str | None = Query(None)) -> dict[str, Any]:
    return {"index": read_index(path)}


@router.get("/api/index/validate")
async def index_validate_route(path: str | None = Query(None)) -> dict[str, Any]:
    return {"report": validate_index(path)}


@router.post("/api/generator/run")
async def generator_run(body: dict[str, Any]) -> dict[str, Any]:
    raise Datam8NotImplementedError(
        message="Generator runs are Jobs-only. Use POST /jobs with type 'generate'.",
        details={"deprecatedEndpoint": "/api/generator/run"},
        hint="Create a job via POST /jobs and subscribe via GET /jobs/{jobId}/events.",
    )


@router.get("/api/base/entities")
async def base_entities(path: str | None = Query(None)) -> dict[str, Any]:
    entities = [e.__dict__ for e in list_base_entities(path)]
    return {"count": len(entities), "entities": entities}


@router.post("/api/base/entities")
async def base_entities_save(body: SaveEntityBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        abs_path = write_base_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = write_base_entity(body.relPath, body.content, body.solutionPath)
    return {"message": "saved", "absPath": abs_path}


@router.delete("/api/base/entities")
async def base_entities_delete(body: DeleteEntityBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        abs_path = delete_base_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = delete_base_entity(body.relPath, body.solutionPath)
    return {"message": "deleted", "absPath": abs_path}


@router.get("/api/fs/list")
async def fs_list(path: str | None = Query(None)) -> dict[str, Any]:
    return {"entries": list_directory(path)}


@router.get("/api/model/function/source")
async def model_function_source_get(
    relPath: str = Query(""),
    source: str = Query(""),
    entityName: str | None = Query(None),
    solutionPath: str | None = Query(None),
) -> dict[str, Any]:
    content = read_function_source(relPath, source, solutionPath, entityName)
    return {"content": content}


class FunctionSourceSaveBody(BaseModel):
    relPath: str
    source: str
    entityName: str | None = None
    content: str
    solutionPath: str | None = None


@router.post("/api/model/function/source")
async def model_function_source_save(body: FunctionSourceSaveBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
        abs_path = write_function_source(body.relPath, body.source, body.content, body.solutionPath, body.entityName)
    return {"message": "saved", "absPath": abs_path}


class FunctionSourceRenameBody(BaseModel):
    relPath: str
    fromSource: str
    toSource: str
    entityName: str | None = None
    solutionPath: str | None = None


@router.post("/api/model/function/rename")
async def model_function_source_rename(body: FunctionSourceRenameBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
        result = rename_function_source(body.relPath, body.fromSource, body.toSource, body.solutionPath, body.entityName)
    return {"message": "renamed", **result}


@router.get("/api/script/list")
async def script_list(path: str = Query(...), solutionPath: str | None = Query(None)) -> dict[str, Any]:
    scripts = list_function_sources(path, solutionPath, None, include_unreferenced=True)
    return {"count": len(scripts), "scripts": scripts}


@router.delete("/api/script/delete")
async def script_delete(
    path: str = Query(...),
    source: str = Query(...),
    solutionPath: str | None = Query(None),
) -> dict[str, Any]:
    resolved, _sol = read_solution(solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
        abs_path = delete_function_source(path, source, solutionPath, None)
    return {"message": "deleted", "absPath": abs_path}


@router.get("/api/search/entities")
async def search_entities_route(q: str = Query(...), path: str | None = Query(None)) -> dict[str, Any]:
    return search_entities(solution_path=path, query=q)


@router.get("/api/search/text")
async def search_text_route(q: str = Query(...), path: str | None = Query(None)) -> dict[str, Any]:
    return search_text(solution_path=path, pattern=q)


class RefactorKeysBody(BaseModel):
    solutionPath: str | None = None
    mapping: dict[str, str]
    apply: bool = False


@router.post("/api/refactor/keys")
async def refactor_keys_route(body: RefactorKeysBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
            result = refactor_keys(solution_path=body.solutionPath, renames=body.mapping, apply=True)
    else:
        result = refactor_keys(solution_path=body.solutionPath, renames=body.mapping, apply=False)
    return {"message": "refactored", "dryRun": not body.apply, "result": result}


class RefactorValuesBody(BaseModel):
    solutionPath: str | None = None
    old: str
    new: str
    key: str | None = None
    apply: bool = False


@router.post("/api/refactor/values")
async def refactor_values_route(body: RefactorValuesBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
            result = refactor_values(solution_path=body.solutionPath, old=body.old, new=body.new, key=body.key, apply=True)
    else:
        result = refactor_values(solution_path=body.solutionPath, old=body.old, new=body.new, key=body.key, apply=False)
    return {"message": "refactored", "dryRun": not body.apply, "result": result}


class RefactorEntityIdBody(BaseModel):
    solutionPath: str | None = None
    old: int
    new: int
    apply: bool = False


@router.post("/api/refactor/entity-id")
async def refactor_entity_id_route(body: RefactorEntityIdBody) -> dict[str, Any]:
    resolved, _sol = read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds("10s")):
            result = refactor_entity_id(solution_path=body.solutionPath, old=body.old, new=body.new, apply=True)
    else:
        result = refactor_entity_id(solution_path=body.solutionPath, old=body.old, new=body.new, apply=False)
    return {"message": "refactored", "dryRun": not body.apply, "result": result}


# ---- Connectors + Plugins (Phase 2) ----


@router.get("/api/connectors")
async def connectors() -> dict[str, Any]:
    # Plugins only (Option 3): scan DATAM8_PLUGIN_DIR/connectors/*
    from datam8.core.connectors.plugin_host import discover_connectors

    connectors, _errors = discover_connectors(plugin_dir=PLUGIN_DIR)
    return {"connectors": [c.to_summary() for c in connectors]}


@router.get("/api/connectors/{connectorId}/ui-schema")
async def connector_ui_schema(connectorId: str) -> dict[str, Any]:
    plugin = get_connector(plugin_dir=PLUGIN_DIR, connector_id=connectorId)
    schema = load_ui_schema(plugin=plugin)
    return {"connectorId": plugin.id, "version": plugin.version, "schema": schema}


class ValidateConnectionBody(BaseModel):
    solutionPath: str | None = None
    extendedProperties: dict[str, Any] | None = None
    runtimeSecrets: dict[str, str] | None = None


@router.post("/api/connectors/{connectorId}/validate-connection")
async def connector_validate_connection(connectorId: str, body: ValidateConnectionBody) -> dict[str, Any]:
    plugin = get_connector(plugin_dir=PLUGIN_DIR, connector_id=connectorId)
    return validate_connection(
        plugin=plugin,
        solution_path=body.solutionPath,
        extended_properties=body.extendedProperties or {},
        runtime_secret_overrides=body.runtimeSecrets or None,
    )


@router.get("/api/plugins")
async def plugins_state() -> dict[str, Any]:
    _ensure_plugins_loaded()
    return _plugin_state


@router.post("/api/plugins/reload")
async def plugins_reload() -> dict[str, Any]:
    global _plugin_state, _plugins_loaded
    _plugin_state = reload_plugins(PLUGIN_DIR)
    _plugins_loaded = True
    return _plugin_state


@router.post("/api/plugins/install")
async def plugins_install(req: Request) -> dict[str, Any]:
    global _plugin_state, _plugins_loaded
    content_type = (req.headers.get("content-type") or "").lower()
    if "application/zip" in content_type:
        zip_bytes = await req.body()
        file_name = req.headers.get("x-file-name")
        install_zip(plugin_dir=PLUGIN_DIR, zip_bytes=zip_bytes, file_name=file_name)
        _plugin_state = reload_plugins(PLUGIN_DIR)
        _plugins_loaded = True
        return _plugin_state
    if "application/json" in content_type:
        body = await req.json()
        git_url = body.get("gitUrl") if isinstance(body, dict) else None
        if not isinstance(git_url, str) or not git_url.strip():
            raise Datam8ValidationError(message="gitUrl is required.", details=None)
        install_git_url(plugin_dir=PLUGIN_DIR, git_url=git_url)
        _plugin_state = reload_plugins(PLUGIN_DIR)
        _plugins_loaded = True
        return _plugin_state
    raise Datam8NotImplementedError(message="Only ZIP or GitHub gitUrl plugin installation is supported.")


class PluginIdBody(BaseModel):
    id: str


@router.post("/api/plugins/enable")
async def plugins_enable(body: PluginIdBody) -> dict[str, Any]:
    global _plugin_state, _plugins_loaded
    set_enabled(PLUGIN_DIR, body.id, True)
    _plugin_state = reload_plugins(PLUGIN_DIR)
    _plugins_loaded = True
    return _plugin_state


@router.post("/api/plugins/disable")
async def plugins_disable(body: PluginIdBody) -> dict[str, Any]:
    global _plugin_state, _plugins_loaded
    set_enabled(PLUGIN_DIR, body.id, False)
    _plugin_state = reload_plugins(PLUGIN_DIR)
    _plugins_loaded = True
    return _plugin_state


@router.post("/api/plugins/uninstall")
async def plugins_uninstall(body: PluginIdBody) -> dict[str, Any]:
    global _plugin_state, _plugins_loaded
    uninstall(PLUGIN_DIR, body.id)
    _plugin_state = reload_plugins(PLUGIN_DIR)
    _plugins_loaded = True
    return _plugin_state


# --- Datasource metadata routes (wizard + base editor) ---


class DataSourceAuthBody(BaseModel):
    solutionPath: str
    runtimeSecrets: dict[str, str] | None = None


@router.post("/api/datasources/{dataSourceId}/list-tables")
async def datasources_list_tables(dataSourceId: str, body: DataSourceAuthBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(message=f"Connector '{manifest.get('id')}' does not support metadata operations.", details=None)
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    return {"tables": tables}


# Legacy compatibility (UI wizard): /api/sources/:name/tables
class ListSourceTablesBody(BaseModel):
    solutionPath: str | None = None
    runtimeSecrets: dict[str, str] | None = None


@router.post("/api/sources/{name}/tables")
async def sources_tables(name: str, body: ListSourceTablesBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=name, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(solution_path=body.solutionPath, data_source_id=name, runtime_secrets=merged)
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(message=f"Connector '{manifest.get('id')}' does not support table listing.", details=None)
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    return {"tables": tables}


class TableMetadataBody(DataSourceAuthBody):
    schema_: str = Field(alias="schema")
    table: str


@router.post("/api/datasources/{dataSourceId}/table-metadata")
async def datasources_table_metadata(dataSourceId: str, body: TableMetadataBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if not hasattr(connector_cls, "get_table_metadata"):
        raise Datam8ValidationError(message=f"Connector '{manifest.get('id')}' does not support metadata operations.", details=None)
    metadata = connector_cls.get_table_metadata(cfg, resolver, body.schema_, body.table)  # type: ignore[attr-defined]
    return {"metadata": metadata}


class HttpVirtualTableBody(DataSourceAuthBody):
    sourceLocation: str


@router.post("/api/http/datasources/{dataSourceId}/virtual-table-metadata")
async def http_virtual_table_metadata(dataSourceId: str, body: HttpVirtualTableBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if manifest.get("id") != "http-api":
        raise Datam8ValidationError(message="DataSource is not configured with an HTTP API connector.", details=None)
    src = (body.sourceLocation or "").strip()
    if not src:
        raise Datam8ValidationError(message="sourceLocation is required.", details=None)
    if hasattr(connector_cls, "get_virtual_table_metadata"):
        return {"metadata": connector_cls.get_virtual_table_metadata(cfg, resolver, src)}  # type: ignore[attr-defined]
    # Fallback: treat `sourceLocation` as a logical "table" name.
    return {"metadata": connector_cls.get_table_metadata(cfg, resolver, "api", src)}  # type: ignore[attr-defined]


@router.get("/api/datasources/{dataSourceId}/usages")
async def datasources_usages(dataSourceId: str, path: str | None = Query(None, alias="path")) -> dict[str, Any]:
    usages = find_data_source_usages(path, dataSourceId)
    return {"usages": usages}


class RefreshPreviewBody(BaseModel):
    solutionPath: str | None = None
    usages: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None


@router.post("/api/datasources/{dataSourceId}/refresh-external-schemas/preview")
async def datasources_refresh_preview(dataSourceId: str, body: RefreshPreviewBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    usage_refs: list[UsageRef] = []
    for u in body.usages or []:
        if not isinstance(u, dict):
            continue
        erp = u.get("entityRelPath")
        si = u.get("sourceIndex")
        if isinstance(erp, str) and isinstance(si, int):
            usage_refs.append(UsageRef(entity_rel_path=erp, source_index=si))
    diffs = preview_schema_changes(solution_path=body.solutionPath, usages=usage_refs, runtime_secrets=merged or None)
    return {"diffs": diffs}


class RefreshApplyBody(BaseModel):
    solutionPath: str | None = None
    diffs: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/api/datasources/{dataSourceId}/refresh-external-schemas/apply")
async def datasources_refresh_apply(dataSourceId: str, body: RefreshApplyBody) -> dict[str, Any]:
    stored = get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    resolved, _sol = read_solution(body.solutionPath)
    if body.noLock:
        updated_entities = apply_schema_changes(solution_path=body.solutionPath, diffs=body.diffs or [], runtime_secrets=merged or None)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            updated_entities = apply_schema_changes(solution_path=body.solutionPath, diffs=body.diffs or [], runtime_secrets=merged or None)
    return {"updatedEntities": updated_entities}


@router.get("/api/secrets/available")
async def secrets_available() -> dict[str, Any]:
    return {"available": bool(is_keyring_available())}


@router.get("/api/secrets/runtime")
async def secrets_runtime_get(
    solutionPath: str | None = Query(None),
    dataSourceName: str = Query(...),
) -> dict[str, Any]:
    if not is_keyring_available():
        return {"runtimeSecrets": None}
    keys = list_runtime_secret_keys(solutionPath, dataSourceName)
    refs: dict[str, str] = {}
    for e in keys:
        k = e.get("key")
        if isinstance(k, str) and k.strip():
            refs[k.strip()] = runtime_secret_ref(data_source_name=dataSourceName, key=k.strip())
    return {"runtimeSecrets": refs or None}


class SecretsRuntimePutBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str
    runtimeSecrets: dict[str, str]


@router.put("/api/secrets/runtime")
async def secrets_runtime_put(body: SecretsRuntimePutBody) -> Response:
    if not is_keyring_available():
        raise Datam8ValidationError(message="Secure secret storage is not available in this mode.", details=None)
    ds = body.dataSourceName
    secrets = {k: (v or "").strip() for k, v in (body.runtimeSecrets or {}).items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    if not secrets:
        return Response(status_code=204)
    for k, v in secrets.items():
        set_runtime_secret(solution_path=body.solutionPath, data_source_name=ds, key=k, value=v)
    return Response(status_code=204)


class SecretsRuntimeDeleteBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str


@router.delete("/api/secrets/runtime")
async def secrets_runtime_delete(body: SecretsRuntimeDeleteBody) -> Response:
    if not is_keyring_available():
        return Response(status_code=204)
    keys = list_runtime_secret_keys(body.solutionPath, body.dataSourceName)
    for e in keys:
        k = e.get("key")
        if isinstance(k, str) and k:
            try:
                delete_runtime_secret(solution_path=body.solutionPath, data_source_name=body.dataSourceName, key=k)
            except Exception:
                continue
    return Response(status_code=204)


class SecretsRuntimeDeleteKeyBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str
    key: str


@router.delete("/api/secrets/runtime/key")
async def secrets_runtime_delete_key(body: SecretsRuntimeDeleteKeyBody) -> Response:
    if not is_keyring_available():
        return Response(status_code=204)
    k = (body.key or "").strip()
    if not k:
        raise Datam8ValidationError(message="key is required.", details=None)
    try:
        delete_runtime_secret(solution_path=body.solutionPath, data_source_name=body.dataSourceName, key=k)
    except Exception:
        return Response(status_code=204)
    return Response(status_code=204)
