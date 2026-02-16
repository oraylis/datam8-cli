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

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from datam8.core import schema_refresh, workspace_io
from datam8.core import secrets as secrets_core
from datam8.core.connectors import plugin_host, plugin_manager
from datam8.core.connectors import resolve as connector_resolve
from datam8.core.errors import (
    Datam8NotFoundError,
    Datam8NotImplementedError,
    Datam8ValidationError,
)
from datam8.core.lock import SolutionLock

from .common import lock_timeout_seconds, plugin_dir
from .response_models import (
    AvailableResponse,
    ConnectorSchemaResponse,
    ConnectorsResponse,
    ConnectorSummaryResponse,
    ConnectorValidateResponse,
    DiffsResponse,
    MetadataResponse,
    PluginStateResponse,
    RuntimeSecretsResponse,
    StatusResponse,
    TablesResponse,
    UpdatedEntitiesResponse,
    UsagesResponse,
)

router = APIRouter()


class ValidateConnectionBody(BaseModel):
    """Request body for connector connection validation."""

    solutionPath: str | None = None
    extendedProperties: dict[str, Any] | None = None
    runtimeSecrets: dict[str, str] | None = None


class PluginIdBody(BaseModel):
    """Request body for plugin id commands."""

    id: str


class DataSourceAuthBody(BaseModel):
    """Request body with datasource auth context."""

    solutionPath: str
    runtimeSecrets: dict[str, str] | None = None


class TableMetadataBody(DataSourceAuthBody):
    """Request body for table metadata lookup."""

    schema_: str = Field(alias="schema")
    table: str


class HttpVirtualTableBody(DataSourceAuthBody):
    """Request body for HTTP virtual-table metadata lookup."""

    sourceLocation: str


class RefreshPreviewBody(BaseModel):
    """Request body for datasource refresh preview."""

    solutionPath: str | None = None
    usages: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None


class RefreshApplyBody(BaseModel):
    """Request body for datasource refresh apply."""

    solutionPath: str | None = None
    diffs: list[dict[str, Any]]
    runtimeSecrets: dict[str, str] | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class SecretsRuntimePutBody(BaseModel):
    """Request body for upserting runtime secrets."""

    solutionPath: str | None = None
    dataSourceName: str
    runtimeSecrets: dict[str, str]


class SecretsRuntimeDeleteBody(BaseModel):
    """Request body for deleting all runtime secrets."""

    solutionPath: str | None = None
    dataSourceName: str


class SecretsRuntimeDeleteKeyBody(BaseModel):
    """Request body for deleting one runtime secret key."""

    solutionPath: str | None = None
    dataSourceName: str
    key: str


class PluginInfoEnvelope(BaseModel):
    """Single-plugin info envelope."""

    plugin: dict[str, Any]


class PluginVerifyResponse(BaseModel):
    """Plugin verification response payload."""

    verified: bool
    plugin: dict[str, Any] | None = None
    bundle: dict[str, Any] | None = None


class RuntimeSecretsListResponse(BaseModel):
    """Runtime secret key list payload."""

    dataSourceName: str
    count: int
    secrets: list[dict[str, Any]]


class RuntimeSecretValueResponse(BaseModel):
    """Single runtime secret value payload."""

    dataSourceName: str
    key: str
    secret: dict[str, Any]


@router.get("/connectors")
async def connectors() -> ConnectorsResponse:
    """List discovered connector plugins."""
    connectors, _errors = plugin_host.discover_connectors(plugin_dir=plugin_dir())
    return ConnectorsResponse(
        connectors=[
            ConnectorSummaryResponse.model_validate(connector.to_summary())
            for connector in connectors
        ]
    )


@router.get("/connectors/{connectorId}/ui-schema")
async def connector_ui_schema(connectorId: str) -> ConnectorSchemaResponse:
    """Load connector UI schema for editor rendering."""
    plugin = plugin_host.get_connector(plugin_dir=plugin_dir(), connector_id=connectorId)
    schema = plugin_host.load_ui_schema(plugin=plugin)
    return ConnectorSchemaResponse(
        connectorId=plugin.id,
        version=plugin.version,
        schema=schema,
    )


@router.post("/connectors/{connectorId}/validate-connection")
async def connector_validate_connection(
    connectorId: str,
    body: ValidateConnectionBody,
) -> ConnectorValidateResponse:
    """Validate datasource connection properties for a connector."""
    plugin = plugin_host.get_connector(plugin_dir=plugin_dir(), connector_id=connectorId)
    result = plugin_host.validate_connection(
        plugin=plugin,
        solution_path=body.solutionPath,
        extended_properties=body.extendedProperties or {},
        runtime_secret_overrides=body.runtimeSecrets or None,
    )
    return ConnectorValidateResponse.model_validate(result)


@router.get("/plugins")
async def plugins_state() -> PluginStateResponse:
    """Return current plugin registry state."""
    return PluginStateResponse.model_validate(plugin_manager.reload(plugin_dir()))


@router.post("/plugins/reload")
async def plugins_reload() -> PluginStateResponse:
    """Reload plugin registry and return updated state."""
    return PluginStateResponse.model_validate(plugin_manager.reload(plugin_dir()))


@router.post("/plugins/install")
async def plugins_install(req: Request) -> PluginStateResponse:
    """Install a plugin from zip payload or git URL."""
    configured_plugin_dir = plugin_dir()
    content_type = (req.headers.get("content-type") or "").lower()
    if "application/zip" in content_type:
        zip_bytes = await req.body()
        file_name = req.headers.get("x-file-name")
        plugin_manager.install_zip(
            plugin_dir=configured_plugin_dir,
            zip_bytes=zip_bytes,
            file_name=file_name,
        )
        return PluginStateResponse.model_validate(
            plugin_manager.reload(configured_plugin_dir)
        )
    if "application/json" in content_type:
        body = await req.json()
        git_url = body.get("gitUrl") if isinstance(body, dict) else None
        if not isinstance(git_url, str) or not git_url.strip():
            raise Datam8ValidationError(message="gitUrl is required.", details=None)
        plugin_manager.install_git_url(
            plugin_dir=configured_plugin_dir,
            git_url=git_url,
        )
        return PluginStateResponse.model_validate(
            plugin_manager.reload(configured_plugin_dir)
        )
    raise Datam8NotImplementedError(
        message="Only ZIP or GitHub gitUrl plugin installation is supported."
    )


@router.post("/plugins/enable")
async def plugins_enable(body: PluginIdBody) -> PluginStateResponse:
    """Enable a plugin by ID."""
    configured_plugin_dir = plugin_dir()
    plugin_manager.set_enabled(configured_plugin_dir, body.id, True)
    return PluginStateResponse.model_validate(plugin_manager.reload(configured_plugin_dir))


@router.post("/plugins/disable")
async def plugins_disable(body: PluginIdBody) -> PluginStateResponse:
    """Disable a plugin by ID."""
    configured_plugin_dir = plugin_dir()
    plugin_manager.set_enabled(configured_plugin_dir, body.id, False)
    return PluginStateResponse.model_validate(plugin_manager.reload(configured_plugin_dir))


@router.post("/plugins/uninstall")
async def plugins_uninstall(body: PluginIdBody) -> PluginStateResponse:
    """Uninstall a plugin by ID."""
    configured_plugin_dir = plugin_dir()
    plugin_manager.uninstall(configured_plugin_dir, body.id)
    return PluginStateResponse.model_validate(plugin_manager.reload(configured_plugin_dir))


@router.get("/plugins/{pluginId}/info")
async def plugin_info(pluginId: str) -> PluginInfoEnvelope:
    """Return metadata for one installed plugin."""
    state = plugin_manager.reload(plugin_dir())
    plugin = next(
        (
            p
            for p in state.get("plugins", [])
            if isinstance(p, dict) and p.get("id") == pluginId
        ),
        None,
    )
    if not plugin:
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": pluginId})
    return PluginInfoEnvelope(plugin=plugin)


@router.post("/plugins/{pluginId}/verify")
async def plugin_verify(pluginId: str) -> PluginVerifyResponse:
    """Verify metadata of one installed plugin."""
    state = plugin_manager.reload(plugin_dir())
    plugin = next(
        (
            p
            for p in state.get("plugins", [])
            if isinstance(p, dict) and p.get("id") == pluginId
        ),
        None,
    )
    if not plugin:
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": pluginId})
    verified = "sha256" in plugin and "entry" in plugin
    return PluginVerifyResponse(verified=verified, plugin=plugin)


@router.post("/plugins/verify")
async def plugins_verify(req: Request) -> PluginVerifyResponse:
    """Verify plugin metadata or validate a ZIP plugin bundle."""
    content_type = (req.headers.get("content-type") or "").lower()
    if "application/zip" in content_type:
        bundle = plugin_manager.verify_zip_bundle(zip_bytes=await req.body())
        return PluginVerifyResponse(verified=True, bundle=asdict(bundle))
    raise Datam8ValidationError(
        message="Only ZIP bundle verification is supported.",
        details=None,
    )


@router.post("/datasources/{dataSourceId}/list-tables")
async def datasources_list_tables(
    dataSourceId: str,
    body: DataSourceAuthBody,
) -> TablesResponse:
    """List available source tables for a datasource connector."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(
        solution_path=body.solutionPath,
        data_source_id=dataSourceId,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(
            message=f"Connector '{manifest.get('id')}' does not support metadata operations.",
            details=None,
        )
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    return TablesResponse(tables=tables)


@router.post("/datasources/{dataSourceId}/test")
async def datasources_test(
    dataSourceId: str,
    body: DataSourceAuthBody,
) -> StatusResponse:
    """Resolve and test datasource connector connectivity."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(
        solution_path=body.solutionPath,
        data_source_id=dataSourceId,
        runtime_secrets=merged,
    )
    if hasattr(connector_cls, "test_connection"):
        connector_cls.test_connection(cfg, resolver)  # type: ignore[attr-defined]
    connector_id = manifest.get("id")
    return StatusResponse(
        status="ok",
        connector=str(connector_id) if connector_id is not None else None,
    )


@router.post("/datasources/{dataSourceId}/table-metadata")
async def datasources_table_metadata(
    dataSourceId: str,
    body: TableMetadataBody,
) -> MetadataResponse:
    """Read table metadata from a datasource connector."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(
        solution_path=body.solutionPath,
        data_source_id=dataSourceId,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "get_table_metadata"):
        raise Datam8ValidationError(
            message=f"Connector '{manifest.get('id')}' does not support metadata operations.",
            details=None,
        )
    metadata = connector_cls.get_table_metadata(
        cfg,
        resolver,
        body.schema_,
        body.table,
    )  # type: ignore[attr-defined]
    return MetadataResponse(metadata=metadata)


@router.post("/http/datasources/{dataSourceId}/virtual-table-metadata")
async def http_virtual_table_metadata(
    dataSourceId: str,
    body: HttpVirtualTableBody,
) -> MetadataResponse:
    """Resolve virtual table metadata for HTTP-based datasources."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    connector_cls, manifest, cfg, resolver = connector_resolve.resolve_and_validate(
        solution_path=body.solutionPath,
        data_source_id=dataSourceId,
        runtime_secrets=merged,
    )
    if manifest.get("id") != "http-api":
        raise Datam8ValidationError(
            message="DataSource is not configured with an HTTP API connector.",
            details=None,
        )
    source_location = (body.sourceLocation or "").strip()
    if not source_location:
        raise Datam8ValidationError(message="sourceLocation is required.", details=None)
    if hasattr(connector_cls, "get_virtual_table_metadata"):
        return MetadataResponse(
            metadata=connector_cls.get_virtual_table_metadata(
                cfg,
                resolver,
                source_location,
            )
        )  # type: ignore[attr-defined]
    return MetadataResponse(
        metadata=connector_cls.get_table_metadata(
            cfg,
            resolver,
            "api",
            source_location,
        )
    )  # type: ignore[attr-defined]


@router.get("/datasources/{dataSourceId}/usages")
async def datasources_usages(
    dataSourceId: str,
    path: str | None = Query(None, alias="path"),
) -> UsagesResponse:
    """Return model usages for a datasource."""
    model_entities = workspace_io.list_model_entities(path)
    usages = schema_refresh.find_data_source_usages(
        path,
        dataSourceId,
        model_entities=model_entities,
    )
    return UsagesResponse(usages=usages)


@router.post("/datasources/{dataSourceId}/refresh-external-schemas/preview")
async def datasources_refresh_preview(
    dataSourceId: str,
    body: RefreshPreviewBody,
) -> DiffsResponse:
    """Preview schema refresh diffs for datasource usages."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    model_entities = workspace_io.list_model_entities(body.solutionPath)
    usage_refs: list[schema_refresh.UsageRef] = []
    for usage in body.usages or []:
        if not isinstance(usage, dict):
            continue
        entity_rel_path = usage.get("entityRelPath")
        source_index = usage.get("sourceIndex")
        if isinstance(entity_rel_path, str) and isinstance(source_index, int):
            usage_refs.append(
                schema_refresh.UsageRef(
                    entity_rel_path=entity_rel_path,
                    source_index=source_index,
                )
            )
    diffs = schema_refresh.preview_schema_changes(
        solution_path=body.solutionPath,
        usages=usage_refs,
        runtime_secrets=merged or None,
        model_entities=model_entities,
    )
    return DiffsResponse(diffs=diffs)


@router.post("/datasources/{dataSourceId}/refresh-external-schemas/apply")
async def datasources_refresh_apply(
    dataSourceId: str,
    body: RefreshApplyBody,
) -> UpdatedEntitiesResponse:
    """Apply schema refresh changes to model entities."""
    stored = secrets_core.get_runtime_secrets_map(
        solution_path=body.solutionPath,
        data_source_name=dataSourceId,
        include_values=True,
    )
    merged = {**stored, **(body.runtimeSecrets or {})}
    model_entities = workspace_io.list_model_entities(body.solutionPath)
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        updated_entities = schema_refresh.apply_schema_changes(
            solution_path=body.solutionPath,
            diffs=body.diffs or [],
            runtime_secrets=merged or None,
            model_entities=model_entities,
        )
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            updated_entities = schema_refresh.apply_schema_changes(
                solution_path=body.solutionPath,
                diffs=body.diffs or [],
                runtime_secrets=merged or None,
                model_entities=model_entities,
            )
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
    for entry in keys:
        key = entry.get("key")
        if isinstance(key, str) and key.strip():
            refs[key.strip()] = secrets_core.runtime_secret_ref(
                data_source_name=dataSourceName,
                key=key.strip(),
            )
    return RuntimeSecretsResponse(runtimeSecrets=refs or None)


@router.get("/secrets/runtime/list")
async def secrets_runtime_list(
    solutionPath: str | None = Query(None),
    dataSourceName: str = Query(...),
) -> RuntimeSecretsListResponse:
    """List runtime secret keys for a datasource."""
    entries = secrets_core.list_runtime_secret_keys(solutionPath, dataSourceName)
    return RuntimeSecretsListResponse(
        dataSourceName=dataSourceName,
        count=len(entries),
        secrets=entries,
    )


@router.get("/secrets/runtime/key")
async def secrets_runtime_get_key(
    solutionPath: str | None = Query(None),
    dataSourceName: str = Query(...),
    key: str = Query(...),
) -> RuntimeSecretValueResponse:
    """Read one runtime secret value for a datasource key."""
    entry = secrets_core.get_runtime_secret(
        solution_path=solutionPath,
        data_source_name=dataSourceName,
        key=key,
        reveal=True,
    )
    return RuntimeSecretValueResponse(
        dataSourceName=dataSourceName,
        key=key,
        secret=entry,
    )


@router.put("/secrets/runtime")
async def secrets_runtime_put(body: SecretsRuntimePutBody) -> Response:
    """Upsert runtime secrets for a datasource."""
    if not secrets_core.is_keyring_available():
        raise Datam8ValidationError(
            message="Secure secret storage is not available in this mode.",
            details=None,
        )
    data_source_name = body.dataSourceName
    secrets = {
        key: (value or "").strip()
        for key, value in (body.runtimeSecrets or {}).items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    if not secrets:
        return Response(status_code=204)
    for key, value in secrets.items():
        secrets_core.set_runtime_secret(
            solution_path=body.solutionPath,
            data_source_name=data_source_name,
            key=key,
            value=value,
        )
    return Response(status_code=204)


@router.delete("/secrets/runtime")
async def secrets_runtime_delete(body: SecretsRuntimeDeleteBody) -> Response:
    """Delete all runtime secrets for a datasource."""
    if not secrets_core.is_keyring_available():
        return Response(status_code=204)
    keys = secrets_core.list_runtime_secret_keys(body.solutionPath, body.dataSourceName)
    for entry in keys:
        key = entry.get("key")
        if isinstance(key, str) and key:
            try:
                secrets_core.delete_runtime_secret(
                    solution_path=body.solutionPath,
                    data_source_name=body.dataSourceName,
                    key=key,
                )
            except Exception:
                continue
    return Response(status_code=204)


@router.delete("/secrets/runtime/key")
async def secrets_runtime_delete_key(body: SecretsRuntimeDeleteKeyBody) -> Response:
    """Delete one runtime secret key for a datasource."""
    if not secrets_core.is_keyring_available():
        return Response(status_code=204)
    key = (body.key or "").strip()
    if not key:
        raise Datam8ValidationError(message="key is required.", details=None)
    try:
        secrets_core.delete_runtime_secret(
            solution_path=body.solutionPath,
            data_source_name=body.dataSourceName,
            key=key,
        )
    except Exception:
        return Response(status_code=204)
    return Response(status_code=204)
