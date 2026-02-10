# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from datam8.cmd.generate import GenerateResult, run_generation
from datam8.core import (
    duration,
    indexing,
    schema_refresh,
    solution_files,
    workspace_io,
)
from datam8.core import (
    migration_v1_to_v2 as migration_v1_to_v2_core,
)
from datam8.core import (
    refactor as refactor_core,
)
from datam8.core import (
    search as search_core,
)
from datam8.core import (
    secrets as secrets_core,
)
from datam8.core.connectors import plugin_host, plugin_manager
from datam8.core.connectors import resolve as connector_resolve
from datam8.core.errors import Datam8NotImplementedError, Datam8ValidationError
from datam8.core.lock import SolutionLock

router = APIRouter()


class AnyPayloadResponse(BaseModel):
    """Flexible typed response for payloads with route-specific keys."""

    model_config = ConfigDict(extra="allow")


class ConfigResponse(BaseModel):
    """Current backend runtime mode."""

    mode: str


class VersionResponse(BaseModel):
    """Version payload."""

    version: str


class SolutionResponse(BaseModel):
    """Solution and resolved path metadata."""

    solution: dict[str, Any]
    resolvedPaths: dict[str, str]


class SolutionFullResponse(BaseModel):
    """Solution and full entity contents."""

    solution: dict[str, Any]
    baseEntities: list[dict[str, Any]]
    modelEntities: list[dict[str, Any]]


class SolutionPathResponse(BaseModel):
    """Path response for created projects."""

    solutionPath: str


class CountEntitiesResponse(BaseModel):
    """Counted list response for entities."""

    count: int
    entities: list[dict[str, Any]]


class MessageWithPathResponse(BaseModel):
    """Standard mutation response with path payload."""

    message: str
    absPath: str


class EntriesResponse(BaseModel):
    """Filesystem listing response."""

    entries: list[dict[str, Any]]


class ContentResponse(BaseModel):
    """Text content response."""

    content: str


class ScriptListResponse(BaseModel):
    """List of scripts."""

    count: int
    scripts: list[Any]


class ConnectorsResponse(BaseModel):
    """Connector summaries."""

    connectors: list[dict[str, Any]]


class ConnectorSchemaResponse(BaseModel):
    """Connector UI schema payload."""

    connectorId: str
    version: str
    schema_: dict[str, Any] = Field(alias="schema")


class TablesResponse(BaseModel):
    """Datasource table list payload."""

    tables: list[dict[str, Any]]


class MetadataResponse(BaseModel):
    """Datasource metadata payload."""

    metadata: dict[str, Any]


class UsagesResponse(BaseModel):
    """Datasource usage payload."""

    usages: list[dict[str, Any]]


class DiffsResponse(BaseModel):
    """Schema refresh preview payload."""

    diffs: list[dict[str, Any]]


class UpdatedEntitiesResponse(BaseModel):
    """Schema refresh apply payload."""

    updatedEntities: list[dict[str, Any]]


class RuntimeSecretsResponse(BaseModel):
    """Runtime secret reference payload."""

    runtimeSecrets: dict[str, str] | None


class AvailableResponse(BaseModel):
    """Boolean capability response."""

    available: bool


def _plugin_dir() -> Path:
    """Resolve the connector plugin directory from env or default location."""
    configured = os.environ.get("DATAM8_PLUGIN_DIR")
    if configured and configured.strip():
        return Path(configured)
    return plugin_manager.default_plugin_dir()


def _lock_timeout_seconds(body: Any) -> float:
    """Parse lock timeout from request body with a safe default."""
    try:
        v = body.get("lockTimeout")
        if isinstance(v, str) and v.strip():
            return duration.parse_duration_seconds(v)
    except Exception:
        pass
    return duration.parse_duration_seconds("10s")



@router.get("/config")
async def config() -> ConfigResponse:
    """Return runtime configuration metadata consumed by the frontend."""
    return ConfigResponse(mode=os.environ.get("DATAM8_MODE") or "server")


@router.get("/solution/inspect")
async def solution_inspect(path: str = Query(...)) -> VersionResponse:
    """Detect and return the solution format version."""
    return VersionResponse(version=solution_files.detect_solution_version(path))


class MigrateV1ToV2Body(BaseModel):
    sourceSolutionPath: str
    targetDir: str
    options: dict[str, Any] | None = None


@router.post("/migration/v1-to-v2")
async def migration_v1_to_v2(body: MigrateV1ToV2Body) -> AnyPayloadResponse:
    """Migrate a v1 solution into v2 structure."""
    args: dict[str, Any] = {"sourceSolutionPath": body.sourceSolutionPath, "targetDir": body.targetDir}
    if body.options is not None:
        args["options"] = body.options
    return AnyPayloadResponse.model_validate(migration_v1_to_v2_core.migrate_solution_v1_to_v2(args))


@router.get("/solution")
async def solution(path: str | None = Query(None)) -> SolutionResponse:
    """Read and return the parsed solution with resolved paths."""
    _resolved, sol = workspace_io.read_solution(path)
    return SolutionResponse(
        solution=sol.model_dump(),
        resolvedPaths={"base": sol.basePath, "model": sol.modelPath},
    )


@router.get("/solution/full")
async def solution_full(path: str | None = Query(None)) -> SolutionFullResponse:
    """Read and return the full solution with base/model entities."""
    _resolved, sol = workspace_io.read_solution(path)
    base_entities = [e.__dict__ for e in workspace_io.list_base_entities(path)]
    model_entities = [e.__dict__ for e in workspace_io.list_model_entities(path)]
    return SolutionFullResponse(
        solution=sol.model_dump(),
        baseEntities=base_entities,
        modelEntities=model_entities,
    )


class NewProjectBody(BaseModel):
    solutionName: str
    projectRoot: str
    basePath: str | None = None
    modelPath: str | None = None
    target: str


@router.post("/solution/new-project")
async def solution_new_project(body: NewProjectBody) -> SolutionPathResponse:
    """Create a new minimal project and return solution path."""
    solution_path = workspace_io.create_new_project(
        solution_name=body.solutionName,
        project_root=body.projectRoot,
        base_path=body.basePath,
        model_path=body.modelPath,
        target=body.target,
    )
    return SolutionPathResponse(solutionPath=solution_path)


@router.get("/model/entities")
async def model_entities(path: str | None = Query(None)) -> CountEntitiesResponse:
    """List model entities for the active solution."""
    entities = [e.__dict__ for e in workspace_io.list_model_entities(path)]
    return CountEntitiesResponse(count=len(entities), entities=entities)


class SaveEntityBody(BaseModel):
    relPath: str
    content: Any
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/model/entities")
async def model_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.write_model_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = workspace_io.write_model_entity(body.relPath, body.content, body.solutionPath)
    return MessageWithPathResponse(message="saved", absPath=abs_path)


class DeleteEntityBody(BaseModel):
    relPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.delete("/model/entities")
async def model_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.delete_model_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = workspace_io.delete_model_entity(body.relPath, body.solutionPath)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


class MoveEntityBody(BaseModel):
    fromRelPath: str
    toRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/model/entities/move")
async def model_entities_move(body: MoveEntityBody) -> AnyPayloadResponse:
    """Move a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.move_model_entity(body.fromRelPath, body.toRelPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = workspace_io.move_model_entity(body.fromRelPath, body.toRelPath, body.solutionPath)
    return AnyPayloadResponse.model_validate({"message": "moved", **result})


class RenameFolderBody(BaseModel):
    fromFolderRelPath: str
    toFolderRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/model/folder/rename")
async def model_folder_rename(body: RenameFolderBody) -> AnyPayloadResponse:
    """Rename a model folder and regenerate index."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.rename_folder(body.fromFolderRelPath, body.toFolderRelPath, body.solutionPath)
        entities = [e.__dict__ for e in workspace_io.list_model_entities(body.solutionPath)]
        workspace_io.regenerate_index(body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = workspace_io.rename_folder(body.fromFolderRelPath, body.toFolderRelPath, body.solutionPath)
            entities = [e.__dict__ for e in workspace_io.list_model_entities(body.solutionPath)]
            workspace_io.regenerate_index(body.solutionPath)
    return AnyPayloadResponse.model_validate({"message": "renamed", **result, "entities": entities})


class RefactorPropertiesBody(BaseModel):
    solutionPath: str | None = None
    propertyRenames: list[dict[str, str]] = Field(default_factory=list)
    valueRenames: list[dict[str, str]] = Field(default_factory=list)
    deletedProperties: list[str] = Field(default_factory=list)
    deletedValues: list[dict[str, str]] = Field(default_factory=list)
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/refactor/properties")
async def refactor_properties_route(body: RefactorPropertiesBody) -> AnyPayloadResponse:
    """Refactor properties/values across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.refactor_properties(
            solution_path=body.solutionPath,
            property_renames=body.propertyRenames,
            value_renames=body.valueRenames,
            deleted_properties=body.deletedProperties,
            deleted_values=body.deletedValues,
        )
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            result = workspace_io.refactor_properties(
                solution_path=body.solutionPath,
                property_renames=body.propertyRenames,
                value_renames=body.valueRenames,
                deleted_properties=body.deletedProperties,
                deleted_values=body.deletedValues,
            )
    return AnyPayloadResponse.model_validate({"message": "refactored", **result})


@router.post("/index/regenerate")
async def index_regenerate(body: dict[str, Any]) -> AnyPayloadResponse:
    """Regenerate and return solution index."""
    solution_path = body.get("solutionPath")
    resolved, _sol = workspace_io.read_solution(solution_path)
    if body.get("noLock"):
        index = workspace_io.regenerate_index(solution_path)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body)):
            index = workspace_io.regenerate_index(solution_path)
    return AnyPayloadResponse.model_validate({"message": "index regenerated", "index": index})


@router.get("/index/show")
async def index_show(path: str | None = Query(None)) -> AnyPayloadResponse:
    """Return current solution index."""
    return AnyPayloadResponse.model_validate({"index": indexing.read_index(path)})


@router.get("/index/validate")
async def index_validate_route(path: str | None = Query(None)) -> AnyPayloadResponse:
    """Return validation report for current index."""
    return AnyPayloadResponse.model_validate({"report": indexing.validate_index(path)})


class GenerateBody(BaseModel):
    solutionPath: str
    target: str
    logLevel: str | None = None
    cleanOutput: bool | None = None
    payloads: list[str] | None = None
    lazy: bool | None = None


@router.post("/generate", response_model=GenerateResult)
async def generator_run(body: GenerateBody) -> GenerateResult:
    return await run_in_threadpool(
        run_generation,
        solution_path=Path(body.solutionPath),
        target=body.target,
        log_level=body.logLevel or "info",
        clean_output=bool(body.cleanOutput),
        payloads=body.payloads or [],
        generate_all=False,
        lazy=bool(body.lazy),
    )


@router.get("/base/entities")
async def base_entities(path: str | None = Query(None)) -> CountEntitiesResponse:
    """List base entities for the active solution."""
    entities = [e.__dict__ for e in workspace_io.list_base_entities(path)]
    return CountEntitiesResponse(count=len(entities), entities=entities)


@router.post("/base/entities")
async def base_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a base entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.write_base_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = workspace_io.write_base_entity(body.relPath, body.content, body.solutionPath)
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/base/entities")
async def base_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a base entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.delete_base_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            abs_path = workspace_io.delete_base_entity(body.relPath, body.solutionPath)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.get("/fs/list")
async def fs_list(path: str | None = Query(None)) -> EntriesResponse:
    """List directory entries inside the active workspace."""
    return EntriesResponse(entries=workspace_io.list_directory(path))


@router.get("/model/function/source")
async def model_function_source_get(
    relPath: str = Query(""),
    source: str = Query(""),
    entityName: str | None = Query(None),
    solutionPath: str | None = Query(None),
) -> ContentResponse:
    """Read model function source content."""
    content = workspace_io.read_function_source(relPath, source, solutionPath, entityName)
    return ContentResponse(content=content)


class FunctionSourceSaveBody(BaseModel):
    relPath: str
    source: str
    entityName: str | None = None
    content: str
    solutionPath: str | None = None


@router.post("/model/function/source")
async def model_function_source_save(body: FunctionSourceSaveBody) -> MessageWithPathResponse:
    """Save model function source content."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
        abs_path = workspace_io.write_function_source(body.relPath, body.source, body.content, body.solutionPath, body.entityName)
    return MessageWithPathResponse(message="saved", absPath=abs_path)


class FunctionSourceRenameBody(BaseModel):
    relPath: str
    fromSource: str
    toSource: str
    entityName: str | None = None
    solutionPath: str | None = None


@router.post("/model/function/rename")
async def model_function_source_rename(body: FunctionSourceRenameBody) -> AnyPayloadResponse:
    """Rename model function source key."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
        result = workspace_io.rename_function_source(body.relPath, body.fromSource, body.toSource, body.solutionPath, body.entityName)
    return AnyPayloadResponse.model_validate({"message": "renamed", **result})


@router.get("/script/list")
async def script_list(path: str = Query(...), solutionPath: str | None = Query(None)) -> ScriptListResponse:
    """List script/function source names for an entity."""
    scripts = workspace_io.list_function_sources(path, solutionPath, None, include_unreferenced=True)
    return ScriptListResponse(count=len(scripts), scripts=scripts)


@router.delete("/script/delete")
async def script_delete(
    path: str = Query(...),
    source: str = Query(...),
    solutionPath: str | None = Query(None),
) -> MessageWithPathResponse:
    """Delete a script/function source file."""
    resolved, _sol = workspace_io.read_solution(solutionPath)
    with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
        abs_path = workspace_io.delete_function_source(path, source, solutionPath, None)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.get("/search/entities")
async def search_entities_route(q: str = Query(...), path: str | None = Query(None)) -> AnyPayloadResponse:
    """Search entities by metadata fields."""
    return AnyPayloadResponse.model_validate(search_core.search_entities(solution_path=path, query=q))


@router.get("/search/text")
async def search_text_route(q: str = Query(...), path: str | None = Query(None)) -> AnyPayloadResponse:
    """Search raw text across solution files."""
    return AnyPayloadResponse.model_validate(search_core.search_text(solution_path=path, pattern=q))


class RefactorKeysBody(BaseModel):
    solutionPath: str | None = None
    mapping: dict[str, str]
    apply: bool = False


@router.post("/refactor/keys")
async def refactor_keys_route(body: RefactorKeysBody) -> AnyPayloadResponse:
    """Refactor property keys across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
            result = refactor_core.refactor_keys(solution_path=body.solutionPath, renames=body.mapping, apply=True)
    else:
        result = refactor_core.refactor_keys(solution_path=body.solutionPath, renames=body.mapping, apply=False)
    return AnyPayloadResponse.model_validate({"message": "refactored", "dryRun": not body.apply, "result": result})


class RefactorValuesBody(BaseModel):
    solutionPath: str | None = None
    old: str
    new: str
    key: str | None = None
    apply: bool = False


@router.post("/refactor/values")
async def refactor_values_route(body: RefactorValuesBody) -> AnyPayloadResponse:
    """Refactor property values across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
            result = refactor_core.refactor_values(solution_path=body.solutionPath, old=body.old, new=body.new, key=body.key, apply=True)
    else:
        result = refactor_core.refactor_values(solution_path=body.solutionPath, old=body.old, new=body.new, key=body.key, apply=False)
    return AnyPayloadResponse.model_validate({"message": "refactored", "dryRun": not body.apply, "result": result})


class RefactorEntityIdBody(BaseModel):
    solutionPath: str | None = None
    old: int
    new: int
    apply: bool = False


@router.post("/refactor/entity-id")
async def refactor_entity_id_route(body: RefactorEntityIdBody) -> AnyPayloadResponse:
    """Refactor entity IDs across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=duration.parse_duration_seconds("10s")):
            result = refactor_core.refactor_entity_id(solution_path=body.solutionPath, old=body.old, new=body.new, apply=True)
    else:
        result = refactor_core.refactor_entity_id(solution_path=body.solutionPath, old=body.old, new=body.new, apply=False)
    return AnyPayloadResponse.model_validate({"message": "refactored", "dryRun": not body.apply, "result": result})


# ---- Connectors + Plugins (Phase 2) ----


@router.get("/connectors")
async def connectors() -> ConnectorsResponse:
    """List discovered connector plugins."""
    connectors, _errors = plugin_host.discover_connectors(plugin_dir=_plugin_dir())
    return ConnectorsResponse(connectors=[c.to_summary() for c in connectors])


@router.get("/connectors/{connectorId}/ui-schema")
async def connector_ui_schema(connectorId: str) -> ConnectorSchemaResponse:
    """Load connector UI schema for editor rendering."""
    plugin = plugin_host.get_connector(plugin_dir=_plugin_dir(), connector_id=connectorId)
    schema = plugin_host.load_ui_schema(plugin=plugin)
    return ConnectorSchemaResponse(connectorId=plugin.id, version=plugin.version, schema=schema)


class ValidateConnectionBody(BaseModel):
    solutionPath: str | None = None
    extendedProperties: dict[str, Any] | None = None
    runtimeSecrets: dict[str, str] | None = None


@router.post("/connectors/{connectorId}/validate-connection")
async def connector_validate_connection(connectorId: str, body: ValidateConnectionBody) -> AnyPayloadResponse:
    """Validate datasource connection properties for a connector."""
    plugin = plugin_host.get_connector(plugin_dir=_plugin_dir(), connector_id=connectorId)
    return AnyPayloadResponse.model_validate(
        plugin_host.validate_connection(
            plugin=plugin,
            solution_path=body.solutionPath,
            extended_properties=body.extendedProperties or {},
            runtime_secret_overrides=body.runtimeSecrets or None,
        )
    )


@router.get("/plugins")
async def plugins_state() -> AnyPayloadResponse:
    """Return current plugin registry state."""
    return AnyPayloadResponse.model_validate(plugin_manager.reload(_plugin_dir()))


@router.post("/plugins/reload")
async def plugins_reload() -> AnyPayloadResponse:
    """Reload plugin registry and return updated state."""
    return AnyPayloadResponse.model_validate(plugin_manager.reload(_plugin_dir()))


@router.post("/plugins/install")
async def plugins_install(req: Request) -> AnyPayloadResponse:
    """Install a plugin from zip payload or git URL."""
    plugin_dir = _plugin_dir()
    content_type = (req.headers.get("content-type") or "").lower()
    if "application/zip" in content_type:
        zip_bytes = await req.body()
        file_name = req.headers.get("x-file-name")
        plugin_manager.install_zip(plugin_dir=plugin_dir, zip_bytes=zip_bytes, file_name=file_name)
        return AnyPayloadResponse.model_validate(plugin_manager.reload(plugin_dir))
    if "application/json" in content_type:
        body = await req.json()
        git_url = body.get("gitUrl") if isinstance(body, dict) else None
        if not isinstance(git_url, str) or not git_url.strip():
            raise Datam8ValidationError(message="gitUrl is required.", details=None)
        plugin_manager.install_git_url(plugin_dir=plugin_dir, git_url=git_url)
        return AnyPayloadResponse.model_validate(plugin_manager.reload(plugin_dir))
    raise Datam8NotImplementedError(message="Only ZIP or GitHub gitUrl plugin installation is supported.")


class PluginIdBody(BaseModel):
    id: str


@router.post("/plugins/enable")
async def plugins_enable(body: PluginIdBody) -> AnyPayloadResponse:
    """Enable a plugin by ID."""
    plugin_dir = _plugin_dir()
    plugin_manager.set_enabled(plugin_dir, body.id, True)
    return AnyPayloadResponse.model_validate(plugin_manager.reload(plugin_dir))


@router.post("/plugins/disable")
async def plugins_disable(body: PluginIdBody) -> AnyPayloadResponse:
    """Disable a plugin by ID."""
    plugin_dir = _plugin_dir()
    plugin_manager.set_enabled(plugin_dir, body.id, False)
    return AnyPayloadResponse.model_validate(plugin_manager.reload(plugin_dir))


@router.post("/plugins/uninstall")
async def plugins_uninstall(body: PluginIdBody) -> AnyPayloadResponse:
    """Uninstall a plugin by ID."""
    plugin_dir = _plugin_dir()
    plugin_manager.uninstall(plugin_dir, body.id)
    return AnyPayloadResponse.model_validate(plugin_manager.reload(plugin_dir))


# --- Datasource metadata routes (wizard + base editor) ---


class DataSourceAuthBody(BaseModel):
    solutionPath: str
    runtimeSecrets: dict[str, str] | None = None


@router.post("/datasources/{dataSourceId}/list-tables")
async def datasources_list_tables(dataSourceId: str, body: DataSourceAuthBody) -> TablesResponse:
    """List available source tables for a datasource connector."""
    stored = secrets_core.get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(message=f"Connector '{manifest.get('id')}' does not support metadata operations.", details=None)
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    return TablesResponse(tables=tables)

class TableMetadataBody(DataSourceAuthBody):
    schema_: str = Field(alias="schema")
    table: str


@router.post("/datasources/{dataSourceId}/table-metadata")
async def datasources_table_metadata(dataSourceId: str, body: TableMetadataBody) -> MetadataResponse:
    """Read table metadata from a datasource connector."""
    stored = secrets_core.get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if not hasattr(connector_cls, "get_table_metadata"):
        raise Datam8ValidationError(message=f"Connector '{manifest.get('id')}' does not support metadata operations.", details=None)
    metadata = connector_cls.get_table_metadata(cfg, resolver, body.schema_, body.table)  # type: ignore[attr-defined]
    return MetadataResponse(metadata=metadata)


class HttpVirtualTableBody(DataSourceAuthBody):
    sourceLocation: str


@router.post("/http/datasources/{dataSourceId}/virtual-table-metadata")
async def http_virtual_table_metadata(dataSourceId: str, body: HttpVirtualTableBody) -> MetadataResponse:
    """Resolve virtual table metadata for HTTP-based datasources."""
    stored = secrets_core.get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(solution_path=body.solutionPath, data_source_id=dataSourceId, runtime_secrets=merged)
    if manifest.get("id") != "http-api":
        raise Datam8ValidationError(message="DataSource is not configured with an HTTP API connector.", details=None)
    src = (body.sourceLocation or "").strip()
    if not src:
        raise Datam8ValidationError(message="sourceLocation is required.", details=None)
    if hasattr(connector_cls, "get_virtual_table_metadata"):
        return MetadataResponse(metadata=connector_cls.get_virtual_table_metadata(cfg, resolver, src))  # type: ignore[attr-defined]
    # Fallback: treat `sourceLocation` as a logical "table" name.
    return MetadataResponse(metadata=connector_cls.get_table_metadata(cfg, resolver, "api", src))  # type: ignore[attr-defined]


@router.get("/datasources/{dataSourceId}/usages")
async def datasources_usages(dataSourceId: str, path: str | None = Query(None, alias="path")) -> UsagesResponse:
    """Return model usages for a datasource."""
    usages = schema_refresh.find_data_source_usages(path, dataSourceId)
    return UsagesResponse(usages=usages)


class RefreshPreviewBody(BaseModel):
    solutionPath: str | None = None
    usages: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None


@router.post("/datasources/{dataSourceId}/refresh-external-schemas/preview")
async def datasources_refresh_preview(dataSourceId: str, body: RefreshPreviewBody) -> DiffsResponse:
    """Preview schema refresh diffs for datasource usages."""
    stored = secrets_core.get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    usage_refs: list[schema_refresh.UsageRef] = []
    for u in body.usages or []:
        if not isinstance(u, dict):
            continue
        erp = u.get("entityRelPath")
        si = u.get("sourceIndex")
        if isinstance(erp, str) and isinstance(si, int):
            usage_refs.append(schema_refresh.UsageRef(entity_rel_path=erp, source_index=si))
    diffs = schema_refresh.preview_schema_changes(solution_path=body.solutionPath, usages=usage_refs, runtime_secrets=merged or None)
    return DiffsResponse(diffs=diffs)


class RefreshApplyBody(BaseModel):
    solutionPath: str | None = None
    diffs: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


@router.post("/datasources/{dataSourceId}/refresh-external-schemas/apply")
async def datasources_refresh_apply(dataSourceId: str, body: RefreshApplyBody) -> UpdatedEntitiesResponse:
    """Apply schema refresh changes to model entities."""
    stored = secrets_core.get_runtime_secrets_map(solution_path=body.solutionPath, data_source_name=dataSourceId, include_values=True)
    merged = {**stored, **(body.runtimeSecrets or {})}
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        updated_entities = schema_refresh.apply_schema_changes(solution_path=body.solutionPath, diffs=body.diffs or [], runtime_secrets=merged or None)
    else:
        with SolutionLock(resolved.root_dir / ".datam8.lock", timeout_seconds=_lock_timeout_seconds(body.model_dump())):
            updated_entities = schema_refresh.apply_schema_changes(solution_path=body.solutionPath, diffs=body.diffs or [], runtime_secrets=merged or None)
    return UpdatedEntitiesResponse(updatedEntities=updated_entities)


@router.get("/secrets/available")
async def secrets_available() -> AvailableResponse:
    """Return whether runtime secret storage is available."""
    return AvailableResponse(available=bool(secrets_core.is_keyring_available()))


@router.get("/secrets/runtime")
async def secrets_runtime_get(
    solutionPath: str | None = Query(None),
    dataSourceName: str = Query(...),
) -> RuntimeSecretsResponse:
    """List runtime secret refs for a datasource."""
    if not secrets_core.is_keyring_available():
        return RuntimeSecretsResponse(runtimeSecrets=None)
    keys = secrets_core.list_runtime_secret_keys(solutionPath, dataSourceName)
    refs: dict[str, str] = {}
    for e in keys:
        k = e.get("key")
        if isinstance(k, str) and k.strip():
            refs[k.strip()] = secrets_core.runtime_secret_ref(data_source_name=dataSourceName, key=k.strip())
    return RuntimeSecretsResponse(runtimeSecrets=refs or None)


class SecretsRuntimePutBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str
    runtimeSecrets: dict[str, str]


@router.put("/secrets/runtime")
async def secrets_runtime_put(body: SecretsRuntimePutBody) -> Response:
    """Upsert runtime secrets for a datasource."""
    if not secrets_core.is_keyring_available():
        raise Datam8ValidationError(message="Secure secret storage is not available in this mode.", details=None)
    ds = body.dataSourceName
    secrets = {k: (v or "").strip() for k, v in (body.runtimeSecrets or {}).items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    if not secrets:
        return Response(status_code=204)
    for k, v in secrets.items():
        secrets_core.set_runtime_secret(solution_path=body.solutionPath, data_source_name=ds, key=k, value=v)
    return Response(status_code=204)


class SecretsRuntimeDeleteBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str


@router.delete("/secrets/runtime")
async def secrets_runtime_delete(body: SecretsRuntimeDeleteBody) -> Response:
    """Delete all runtime secrets for a datasource."""
    if not secrets_core.is_keyring_available():
        return Response(status_code=204)
    keys = secrets_core.list_runtime_secret_keys(body.solutionPath, body.dataSourceName)
    for e in keys:
        k = e.get("key")
        if isinstance(k, str) and k:
            try:
                secrets_core.delete_runtime_secret(solution_path=body.solutionPath, data_source_name=body.dataSourceName, key=k)
            except Exception:
                continue
    return Response(status_code=204)


class SecretsRuntimeDeleteKeyBody(BaseModel):
    solutionPath: str | None = None
    dataSourceName: str
    key: str


@router.delete("/secrets/runtime/key")
async def secrets_runtime_delete_key(body: SecretsRuntimeDeleteKeyBody) -> Response:
    """Delete one runtime secret key for a datasource."""
    if not secrets_core.is_keyring_available():
        return Response(status_code=204)
    k = (body.key or "").strip()
    if not k:
        raise Datam8ValidationError(message="key is required.", details=None)
    try:
        secrets_core.delete_runtime_secret(solution_path=body.solutionPath, data_source_name=body.dataSourceName, key=k)
    except Exception:
        return Response(status_code=204)
    return Response(status_code=204)



