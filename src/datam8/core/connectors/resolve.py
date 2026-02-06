from __future__ import annotations

import os
from typing import Any

from pathlib import Path

from datam8.core.connectors.binding import decode_connector_binding
from datam8.core.connectors.plugin_host import (
    SecretResolver,
    get_connector,
    load_connector_class,
    require_version,
    validate_connection as validate_connection_via_plugin,
)
from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8NotFoundError,
    Datam8ValidationError,
)
from datam8.core.connectors.plugin_manager import default_plugin_dir
from datam8.core.workspace_io import list_base_entities


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _plugin_dir() -> Path:
    return Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))


def load_data_source_context(solution_path: str | None, data_source_id: str) -> dict[str, Any]:
    base_entities = list_base_entities(solution_path)

    data_sources_file = next((e for e in base_entities if e.name == "DataSources"), None)
    if not data_sources_file:
        raise Datam8NotFoundError(message="DataSources.json not found in solution.", details=None)
    ds_list = (data_sources_file.content or {}).get("dataSources") if isinstance(data_sources_file.content, dict) else None
    if not isinstance(ds_list, list):
        raise Datam8ValidationError(message="DataSources.json is missing a dataSources array.", details=None)
    data_source = next((ds for ds in ds_list if isinstance(ds, dict) and ds.get("name") == data_source_id), None)
    if not data_source:
        raise Datam8NotFoundError(message=f"DataSource '{data_source_id}' not found.", details=None)

    data_source_types_file = next((e for e in base_entities if e.name == "DataSourceTypes"), None)
    if not data_source_types_file:
        raise Datam8NotFoundError(message="DataSourceTypes.json not found in solution.", details=None)
    types_list = (data_source_types_file.content or {}).get("dataSourceTypes") if isinstance(data_source_types_file.content, dict) else None
    if not isinstance(types_list, list):
        raise Datam8ValidationError(message="DataSourceTypes.json is missing a dataSourceTypes array.", details=None)

    type_name = data_source.get("type") or data_source.get("dataSourceType")
    if not isinstance(type_name, str) or not type_name.strip():
        raise Datam8ValidationError(message=f"DataSource '{data_source_id}' is missing a type name.", details=None)
    data_source_type = next((t for t in types_list if isinstance(t, dict) and t.get("name") == type_name), None)
    if not data_source_type:
        raise Datam8NotFoundError(message=f"DataSourceType '{type_name}' not found.", details=None)

    return {"dataSource": data_source, "dataSourceType": data_source_type}

def resolve_and_validate(
    *,
    solution_path: str | None,
    data_source_id: str,
    runtime_secrets: dict[str, str] | None,
) -> tuple[Any, dict[str, Any], dict[str, str], SecretResolver]:
    ctx = load_data_source_context(solution_path, data_source_id)
    data_source = ctx["dataSource"]
    data_source_type = ctx["dataSourceType"]
    binding = decode_connector_binding(data_source_type.get("connectionProperties"))
    if not binding:
        raise Datam8ValidationError(
            code="connector_missing",
            message=f"DataSourceType '{data_source_type.get('name')}' has no connector binding.",
            details={"dataSourceType": data_source_type.get("name")},
        )

    plugin = get_connector(plugin_dir=_plugin_dir(), connector_id=binding.connector_id)
    require_version(plugin=plugin, version_req=binding.version_req)
    connector_cls = load_connector_class(plugin)

    raw_props = data_source.get("extendedProperties") if isinstance(data_source, dict) else None
    if raw_props is None:
        raw_props = {}
    if not _is_record(raw_props):
        raise Datam8ValidationError(message=f"Invalid extendedProperties for DataSource '{data_source_id}'. Expected an object.", details=None)

    # Enforce string-only extendedProperties (normalize to strings).
    props: dict[str, str] = {}
    for k, v in raw_props.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if v is None:
            continue
        props[k] = v if isinstance(v, str) else str(v)

    overrides = {k: (v or "").strip() for k, v in (runtime_secrets or {}).items() if isinstance(k, str) and isinstance(v, str) and v.strip()}

    validation = validate_connection_via_plugin(
        plugin=plugin,
        solution_path=solution_path,
        extended_properties=props,
        runtime_secret_overrides=overrides or None,
    )
    if not validation.get("ok"):
        raise Datam8ValidationError(
            message=f"Invalid connection config for DataSource '{data_source_id}' ({plugin.id}).",
            details={"errors": validation.get("errors") or []},
        )

    resolver = SecretResolver(solution_path=solution_path, overrides=overrides or None)
    return connector_cls, plugin.to_summary(), props, resolver
