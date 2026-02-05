from __future__ import annotations

from typing import Any

from datam8.core.connectors.registry import connector_registry
from datam8.core.connectors.validation import validate_connection_config
from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8NotFoundError,
    Datam8ValidationError,
)
from datam8.core.workspace_io import list_base_entities


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _get_bound_connector_id(data_source_type: dict[str, Any]) -> str | None:
    ext = data_source_type.get("extendedProperties")
    if not isinstance(ext, dict):
        return None
    connector = ext.get("connector")
    if not isinstance(connector, dict):
        return None
    cid = connector.get("id")
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    return None


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


def resolve_connector_module(data_source_type: dict[str, Any]):
    bound_id = _get_bound_connector_id(data_source_type)
    if bound_id:
        mod = connector_registry.resolve_by_id(bound_id)
        if not mod:
            raise Datam8ExternalSystemError(
                code="connector_missing",
                message=f"Connector '{bound_id}' is linked on DataSourceType '{data_source_type.get('name')}' but is not registered.",
                details=None,
            )
        return mod

    alias = str(data_source_type.get("name") or "")
    mod = connector_registry.resolve_by_alias(alias)
    if not mod:
        raise Datam8ExternalSystemError(code="connector_missing", message=f"No connector registered for DataSourceType '{alias}'.", details=None)
    return mod


def resolve_and_validate(
    *,
    solution_path: str | None,
    data_source_id: str,
    runtime_secrets: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str], list[str]]:
    ctx = load_data_source_context(solution_path, data_source_id)
    data_source = ctx["dataSource"]
    data_source_type = ctx["dataSourceType"]
    module = resolve_connector_module(data_source_type)
    manifest = module.manifest

    raw_cfg = data_source.get("extendedProperties") if isinstance(data_source, dict) else None
    if raw_cfg is None:
        raw_cfg = {}
    if not _is_record(raw_cfg):
        raise Datam8ValidationError(
            message=f"Invalid extendedProperties for DataSource '{data_source_id}'. Expected an object.",
            details=None,
        )

    validation = validate_connection_config(manifest, raw_cfg)
    if not validation.ok:
        raise Datam8ValidationError(
            message=f"Invalid connection config for DataSource '{data_source_id}' ({manifest.get('name')}): " +
            ", ".join([f"{e['path']}: {e['message']}" for e in validation.errors]),
            details={"errors": validation.errors},
        )

    secrets = {k: (v or "").strip() for k, v in (runtime_secrets or {}).items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    missing = [k for k in validation.required_secrets if not secrets.get(k)]
    if missing:
        raise Datam8ValidationError(message=f"Missing required secrets: {', '.join(missing)}", details={"missing": missing})

    return module, manifest, validation.config, secrets, validation.required_secrets
