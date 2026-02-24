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

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from datam8.core.connectors.resolve import resolve_and_validate
from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8PermissionError,
    Datam8ValidationError,
)
from datam8.core.workspace_io import (
    ModelEntityEntry,
    list_base_entities,
    list_model_entities,
    write_model_entity,
)
from datam8_model import attribute as attribute_model
from datam8_model import base as base_model
from datam8_model import data_type as data_type_model
from datam8_model import model as model_model

DataType = dict[str, Any]
ModelEntityInput = ModelEntityEntry | dict[str, Any]


def _opt_int_gt0(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and float(v).is_integer() and int(v) > 0:
        return int(v)
    return None


def _opt_int_gte0(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and float(v).is_integer() and int(v) >= 0:
        return int(v)
    return None


def sanitize_data_type(input_value: Any) -> DataType:
    """Sanitize data type."""
    raw = input_value if isinstance(input_value, dict) else None

    if isinstance(raw, dict) and isinstance(raw.get("type"), str):
        t = raw.get("type")
    elif isinstance(input_value, str):
        t = input_value
    else:
        t = "string"

    if isinstance(raw, dict) and isinstance(raw.get("nullable"), bool):
        nullable = bool(raw.get("nullable"))
    elif isinstance(input_value, dict) and isinstance(input_value.get("nullable"), bool):
        nullable = bool(input_value.get("nullable"))
    else:
        nullable = True

    rest: dict[str, Any] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k in {"charLen", "precision", "scale", "nullable", "type"}:
                continue
            rest[k] = v

    out: DataType = {**rest, "type": str(t), "nullable": bool(nullable)}

    if isinstance(raw, dict):
        char_len = _opt_int_gt0(raw.get("charLen"))
        if char_len is not None:
            out["charLen"] = char_len
        precision = _opt_int_gt0(raw.get("precision"))
        if precision is not None:
            out["precision"] = precision
        scale = _opt_int_gte0(raw.get("scale"))
        if scale is not None:
            out["scale"] = scale

    return out


def normalize_data_type(dt: Any) -> DataType:
    """Normalize data type."""
    return sanitize_data_type(dt)


def is_same_data_type(a: Any, b: Any) -> bool:
    """Is same data type."""
    left = sanitize_data_type(a)
    right = sanitize_data_type(b)
    return (
        left.get("type") == right.get("type")
        and left.get("charLen") == right.get("charLen")
        and left.get("precision") == right.get("precision")
        and left.get("scale") == right.get("scale")
    )


def safe_merge_data_type(current: Any, source: Any) -> DataType:
    """Safe merge data type."""
    current_s = sanitize_data_type(current)
    source_s = sanitize_data_type(source)
    merged: DataType = {**current_s, **source_s}
    merged["type"] = source_s.get("type")
    merged["nullable"] = source_s.get("nullable")
    return merged


def _split_source_location(source_location: str) -> tuple[str, str]:
    src = (source_location or "").strip()
    if not src:
        return "", ""

    m = re.match(r"^\[(.*?)\]\.\[(.*?)\]$", src)
    if m:
        return m.group(1), m.group(2)

    parts = src.split(".")
    if len(parts) == 2:
        return parts[0], parts[1]

    return "", src


def _data_type_payload(value: data_type_model.DataType | DataType | str | None) -> DataType | str | None:
    if isinstance(value, data_type_model.DataType):
        return value.model_dump(mode="json")
    return value


def _to_data_type_model(value: Any) -> data_type_model.DataType:
    return data_type_model.DataType.model_validate(sanitize_data_type(value))


def _coerce_model_entity_entry(value: ModelEntityInput) -> ModelEntityEntry | None:
    if isinstance(value, ModelEntityEntry):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return ModelEntityEntry.model_validate(value)
    except Exception:
        return None


def _list_model_entities(solution_path: str | None) -> list[ModelEntityEntry]:
    return list_model_entities(solution_path)


def _resolved_model_entities(
    *,
    solution_path: str | None,
    model_entities: Sequence[ModelEntityInput] | None,
) -> list[ModelEntityEntry]:
    if model_entities is not None:
        coerced = [_coerce_model_entity_entry(e) for e in model_entities]
        return [e for e in coerced if e is not None]
    return _list_model_entities(solution_path)


def _layer_from_rel_path(rel_path: str) -> str | None:
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    for p in parts:
        if re.match(r"^\d+-", p):
            return p
    return None


def _get_external_source(
    entity: model_model.ModelEntity,
    source_index: int,
) -> model_model.ExternalModelSource | None:
    if source_index < 0 or source_index >= len(entity.sources):
        return None
    source = entity.sources[source_index]
    if isinstance(source, model_model.ExternalModelSource):
        return source
    return None


def find_data_source_usages(
    solution_path: str | None,
    data_source_name: str,
    *,
    model_entities: Sequence[ModelEntityInput] | None = None,
) -> list[dict[str, Any]]:
    """Find data source usages."""
    usages: list[dict[str, Any]] = []
    entities = _resolved_model_entities(solution_path=solution_path, model_entities=model_entities)

    for ent in entities:
        layer = _layer_from_rel_path(ent.relPath)
        for idx, src in enumerate(ent.content.sources):
            if not isinstance(src, model_model.ExternalModelSource):
                continue
            if src.dataSource != data_source_name:
                continue
            usages.append(
                {
                    "entityRelPath": ent.relPath,
                    "entityName": ent.name,
                    "layer": layer,
                    "sourceIndex": idx,
                    "dataSource": src.dataSource,
                    "sourceAlias": src.sourceAlias,
                    "sourceLocation": src.sourceLocation,
                }
            )

    return usages


def _fetch_http_api_virtual_table_metadata_columns(
    *,
    cfg: dict[str, Any],
    resolver: Any,
    source_location: str,
) -> list[dict[str, Any]]:
    base_url = str(cfg.get("baseUrl") or "").rstrip("/")
    src = (source_location or "").strip()
    if not src:
        raise Datam8ValidationError(message="sourceLocation is required.", details=None)
    url = src if src.lower().startswith(("http://", "https://")) else f"{base_url}/{src.lstrip('/')}"

    headers: dict[str, str] = {}
    kind = (cfg.get("auth.kind") if isinstance(cfg.get("auth.kind"), str) else None) or "none"
    auth = None
    if kind == "api-key-header":
        header_name = (cfg.get("auth.headerName") if isinstance(cfg.get("auth.headerName"), str) else None) or "X-API-Key"
        api_key = resolver.resolve(key="apiKey", value=str(cfg.get("apiKey") or ""))
        if api_key:
            headers[str(header_name)] = api_key
    elif kind == "bearer-static":
        token = resolver.resolve(key="token", value=str(cfg.get("token") or ""))
        if token:
            headers["authorization"] = f"Bearer {token}"
    elif kind == "basic":
        username = (cfg.get("auth.username") if isinstance(cfg.get("auth.username"), str) else None) or ""
        password = resolver.resolve(key="password", value=str(cfg.get("password") or ""))
        auth = (username, password)

    timeout_ms = int(cfg.get("requestTimeoutMs") or 10000)

    with httpx.Client(timeout=timeout_ms / 1000.0, follow_redirects=True) as client:
        res = client.get(url, headers=headers, auth=auth)
        if res.status_code in (401, 403):
            raise Datam8PermissionError(code="auth", message="Authentication failed.", details={"status": res.status_code})
        res.raise_for_status()
        data = res.json()

    if not isinstance(data, list):
        raise Datam8ValidationError(message="HTTP response is not a JSON array.", details=None)
    sample = next((x for x in data if isinstance(x, dict)), {})
    cols = []
    for k, v in sample.items():
        dt = "string"
        if isinstance(v, bool):
            dt = "boolean"
        elif isinstance(v, int):
            dt = "int"
        elif isinstance(v, float):
            dt = "double"
        cols.append(
            {
                "name": str(k),
                "dataType": sanitize_data_type({"type": dt, "nullable": True}),
                "isPrimaryKey": False,
            }
        )
    return cols


def fetch_source_metadata(
    *,
    solution_path: str | None,
    data_source_name: str,
    source_location: str,
    runtime_secrets: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """Fetch source metadata."""
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=solution_path,
        data_source_id=data_source_name,
        runtime_secrets=runtime_secrets,
    )

    if hasattr(connector_cls, "get_table_metadata"):
        schema, table = _split_source_location(source_location)
        md = connector_cls.get_table_metadata(cfg, resolver, schema, table)  # type: ignore[attr-defined]
        cols = md.get("columns") if isinstance(md, dict) else None
        if not isinstance(cols, list):
            raise Datam8ExternalSystemError(code="metadata_error", message="Connector metadata response is invalid.", details=None)
        out = []
        for c in cols:
            if not isinstance(c, dict):
                continue
            dt = sanitize_data_type(
                {
                    "type": c.get("dataType") or "string",
                    "nullable": bool(c.get("isNullable", True)),
                    "charLen": c.get("maxLength"),
                    "precision": c.get("numericPrecision"),
                    "scale": c.get("numericScale"),
                }
            )
            out.append({"name": c.get("name"), "dataType": dt, "isPrimaryKey": bool(c.get("isPrimaryKey", False))})
        return out

    if manifest.get("id") == "http-api":
        return _fetch_http_api_virtual_table_metadata_columns(cfg=cfg, resolver=resolver, source_location=source_location)

    raise Datam8ExternalSystemError(
        code="metadata_unavailable",
        message=f"No metadata connector available for data source '{data_source_name}'.",
        details={"connector": manifest.get("id")},
    )


def _get_data_type_mapping(solution_path: str | None, data_source_name: str) -> dict[str, list[dict[str, Any]]]:
    base_entities = list_base_entities(solution_path)
    ds_entry = next((e for e in base_entities if e.name == "DataSources"), None)
    dst_entry = next((e for e in base_entities if e.name == "DataSourceTypes"), None)
    if not ds_entry or not dst_entry:
        return {"sourceMapping": [], "typeMapping": []}

    if not isinstance(ds_entry.content.root, base_model.DataSources):
        return {"sourceMapping": [], "typeMapping": []}
    if not isinstance(dst_entry.content.root, base_model.DataSourceTypes):
        return {"sourceMapping": [], "typeMapping": []}

    ds_list = ds_entry.content.root.dataSources
    dst_list = dst_entry.content.root.dataSourceTypes

    data_source = next((d for d in ds_list if d.name == data_source_name), None)
    if data_source is None:
        return {"sourceMapping": [], "typeMapping": []}

    type_name = data_source.type
    data_source_type = next((t for t in dst_list if t.name == type_name), None)

    source_mapping = [m.model_dump(mode="json") for m in (data_source.dataTypeMapping or [])]
    type_mapping = [m.model_dump(mode="json") for m in (data_source_type.dataTypeMapping if data_source_type else [])]

    return {"sourceMapping": source_mapping, "typeMapping": type_mapping}


def _resolve_target_type(mappings: dict[str, list[dict[str, Any]]], source_type: str) -> str:
    normalized_source = (source_type or "").lower()

    for m in mappings.get("sourceMapping", []):
        if not isinstance(m, dict):
            continue
        if str(m.get("sourceType") or "").lower() == normalized_source and m.get("targetType"):
            return str(m.get("targetType"))
    for m in mappings.get("typeMapping", []):
        if not isinstance(m, dict):
            continue
        if str(m.get("sourceType") or "").lower() == normalized_source and m.get("targetType"):
            return str(m.get("targetType"))

    return source_type


SchemaChangeType = str


@dataclass(frozen=True)
class UsageRef:
    entity_rel_path: str
    source_index: int


def preview_schema_changes(
    *,
    solution_path: str | None,
    usages: list[UsageRef],
    runtime_secrets: dict[str, str] | None,
    model_entities: Sequence[ModelEntityInput] | None = None,
) -> list[dict[str, Any]]:
    """Preview schema changes."""
    diffs: list[dict[str, Any]] = []
    entities = _resolved_model_entities(solution_path=solution_path, model_entities=model_entities)
    entity_map = {e.relPath: e for e in entities}

    for usage in usages:
        ent_entry = entity_map.get(usage.entity_rel_path)
        if not ent_entry:
            continue
        entity = ent_entry.content
        source = _get_external_source(entity, usage.source_index)
        if source is None:
            continue

        source_metadata = fetch_source_metadata(
            solution_path=solution_path,
            data_source_name=source.dataSource,
            source_location=source.sourceLocation,
            runtime_secrets=runtime_secrets,
        )

        mapping = list(source.mapping or [])
        attributes = list(entity.attributes)
        changes: list[dict[str, Any]] = []

        for src_col in source_metadata:
            src_name = src_col.get("name")
            if not isinstance(src_name, str):
                continue
            existing_map = next((m for m in mapping if m.sourceName == src_name), None)
            if not existing_map:
                changes.append(
                    {
                        "changeType": "NEW_COLUMN",
                        "columnName": src_name,
                        "sourceAfter": src_col,
                        "applyToEntitySuggested": True,
                    }
                )
                continue

            existing_type = normalize_data_type(_data_type_payload(existing_map.sourceDataType))
            new_type = sanitize_data_type(src_col.get("dataType"))
            merged_type = safe_merge_data_type(existing_type, new_type)
            source_after = {**src_col, "dataType": merged_type}

            target_name = existing_map.targetName
            attr = next((a for a in attributes if a.name == target_name), None)

            if not is_same_data_type(existing_type, merged_type):
                changes.append(
                    {
                        "changeType": "TYPE_CHANGED",
                        "columnName": src_name,
                        "sourceBefore": {"name": src_name, "dataType": existing_type, "isPrimaryKey": False},
                        "sourceAfter": source_after,
                        "entityAttributeName": attr.name if attr else None,
                        "entityAttributeBefore": attr.model_dump(mode="json") if attr else None,
                        "applyToEntitySuggested": True,
                    }
                )

            if bool(existing_type.get("nullable", True)) != bool(merged_type.get("nullable", True)):
                changes.append(
                    {
                        "changeType": "NULLABILITY_CHANGED",
                        "columnName": src_name,
                        "sourceBefore": {"name": src_name, "dataType": existing_type, "isPrimaryKey": False},
                        "sourceAfter": source_after,
                        "entityAttributeName": attr.name if attr else None,
                        "entityAttributeBefore": attr.model_dump(mode="json") if attr else None,
                        "applyToEntitySuggested": False,
                    }
                )

            if attr:
                attr_is_pk = bool(attr.isBusinessKey or False)
                if bool(src_col.get("isPrimaryKey", False)) != attr_is_pk:
                    changes.append(
                        {
                            "changeType": "PK_CHANGED",
                            "columnName": src_name,
                            "sourceBefore": {"name": src_name, "dataType": existing_type, "isPrimaryKey": attr_is_pk},
                            "sourceAfter": src_col,
                            "entityAttributeName": attr.name,
                            "entityAttributeBefore": attr.model_dump(mode="json"),
                            "applyToEntitySuggested": False,
                        }
                    )

        for map_item in mapping:
            src_name = map_item.sourceName
            exists = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == src_name), None)
            if exists:
                continue
            attr = next((a for a in attributes if a.name == map_item.targetName), None)
            if attr and attr.dateDeleted:
                continue
            changes.append(
                {
                    "changeType": "REMOVED_COLUMN",
                    "columnName": src_name,
                    "sourceBefore": {
                        "name": src_name,
                        "dataType": normalize_data_type(_data_type_payload(map_item.sourceDataType)),
                        "isPrimaryKey": False,
                    },
                    "entityAttributeName": attr.name if attr else None,
                    "entityAttributeBefore": attr.model_dump(mode="json") if attr else None,
                    "applyToEntitySuggested": True,
                }
            )

        if changes:
            diffs.append(
                {
                    "entityRelPath": usage.entity_rel_path,
                    "entityName": ent_entry.name,
                    "sourceIndex": usage.source_index,
                    "dataSource": source.dataSource,
                    "sourceAlias": source.sourceAlias,
                    "sourceLocation": source.sourceLocation,
                    "changes": changes,
                    "summary": {
                        "newColumns": len([c for c in changes if c.get("changeType") == "NEW_COLUMN"]),
                        "removedColumns": len([c for c in changes if c.get("changeType") == "REMOVED_COLUMN"]),
                        "pkChanges": len([c for c in changes if c.get("changeType") == "PK_CHANGED"]),
                        "typeChanges": len([c for c in changes if c.get("changeType") == "TYPE_CHANGED"]),
                        "nullableChanges": len([c for c in changes if c.get("changeType") == "NULLABILITY_CHANGED"]),
                    },
                }
            )

    return diffs


def apply_schema_changes(
    *,
    solution_path: str | None,
    diffs: list[dict[str, Any]],
    runtime_secrets: dict[str, str] | None,
    model_entities: Sequence[ModelEntityInput] | None = None,
) -> list[dict[str, Any]]:
    """Apply schema changes."""
    result: list[dict[str, Any]] = []
    entities = _resolved_model_entities(solution_path=solution_path, model_entities=model_entities)
    entity_map = {e.relPath: e for e in entities}
    mapping_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for diff_item in diffs:
        entity_rel_path = diff_item.get("entityRelPath")
        source_index = diff_item.get("sourceIndex")
        if not isinstance(entity_rel_path, str) or not isinstance(source_index, int):
            continue

        ent_entry = entity_map.get(entity_rel_path)
        if not ent_entry:
            continue

        entity = ent_entry.content
        source = _get_external_source(entity, source_index)
        if source is None:
            continue

        ds_name = source.dataSource
        source_location = source.sourceLocation
        source_metadata = fetch_source_metadata(
            solution_path=solution_path,
            data_source_name=ds_name,
            source_location=source_location,
            runtime_secrets=runtime_secrets,
        )

        mappings = mapping_cache.get(ds_name)
        if not mappings:
            mappings = _get_data_type_mapping(solution_path, ds_name)
            mapping_cache[ds_name] = mappings

        attributes_changed = 0
        mappings_changed = 0
        now = datetime.now(UTC).replace(microsecond=0)

        new_mapping: list[model_model.SourceAttributeMapping] = []
        current_mapping = list(source.mapping or [])

        for src_col in source_metadata:
            if not isinstance(src_col, dict) or not isinstance(src_col.get("name"), str):
                continue
            src_name = src_col["name"]
            existing_map = next((m for m in current_mapping if m.sourceName == src_name), None)
            if existing_map:
                existing_type = normalize_data_type(_data_type_payload(existing_map.sourceDataType))
                new_type = sanitize_data_type(src_col.get("dataType"))
                merged_type = safe_merge_data_type(existing_type, new_type)
                mapping_changed = (not is_same_data_type(existing_type, merged_type)) or bool(existing_type.get("nullable")) != bool(
                    merged_type.get("nullable")
                )
                next_map = existing_map.model_copy(deep=True)
                next_map.sourceDataType = _to_data_type_model(merged_type)
                if mapping_changed:
                    mappings_changed += 1
                new_mapping.append(next_map)
            else:
                mappings_changed += 1
                new_mapping.append(
                    model_model.SourceAttributeMapping(
                        targetName=src_name,
                        sourceName=src_name,
                        sourceDataType=_to_data_type_model(src_col.get("dataType")),
                        properties=[],
                    )
                )

        if len(new_mapping) != len(current_mapping):
            mappings_changed += 1
        source.mapping = new_mapping

        changes_raw = diff_item.get("changes")
        changes = changes_raw if isinstance(changes_raw, list) else []
        attributes = list(entity.attributes)

        for ch in changes:
            if not isinstance(ch, dict) or not ch.get("applyToEntity"):
                continue
            column_name = ch.get("columnName")
            change_type = ch.get("changeType")
            if not isinstance(column_name, str) or not isinstance(change_type, str):
                continue

            map_entry = next((m for m in new_mapping if m.sourceName == column_name), None)
            target_name = map_entry.targetName if map_entry else column_name

            if change_type == "NEW_COLUMN":
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                source_type_simple = sanitize_data_type(src_col.get("dataType")).get("type")
                target_type_name = _resolve_target_type(mappings, str(source_type_simple or "string"))
                new_attr_dt = _to_data_type_model({**sanitize_data_type(src_col.get("dataType")), "type": target_type_name})
                attr = next((a for a in attributes if a.name == target_name), None)
                if attr:
                    if attr.dateDeleted:
                        attr.dateDeleted = None
                        attr.dateModified = now
                        attr.dataType = _to_data_type_model(safe_merge_data_type(_data_type_payload(attr.dataType), new_attr_dt.model_dump(mode="json")))
                        attributes_changed += 1
                else:
                    max_ordinal = max((a.ordinalNumber for a in attributes), default=0)
                    attributes.append(
                        attribute_model.Attribute(
                            name=target_name,
                            attributeType="Physical",
                            ordinalNumber=max_ordinal + 10,
                            dataType=new_attr_dt,
                            dateAdded=now,
                        )
                    )
                    attributes_changed += 1

            elif change_type == "REMOVED_COLUMN":
                attr = next((a for a in attributes if a.name == target_name), None)
                if not attr and isinstance(ch.get("entityAttributeName"), str):
                    ea = ch.get("entityAttributeName")
                    attr = next((a for a in attributes if a.name == ea), None)
                if attr:
                    attr.dateDeleted = now
                    attributes_changed += 1

            elif change_type in {"TYPE_CHANGED", "NULLABILITY_CHANGED"}:
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                attr = next((a for a in attributes if a.name == target_name), None)
                if not attr:
                    continue
                source_type_simple = sanitize_data_type(src_col.get("dataType")).get("type")
                target_type_name = _resolve_target_type(mappings, str(source_type_simple or "string"))
                new_attr_dt = _to_data_type_model({**sanitize_data_type(src_col.get("dataType")), "type": target_type_name})
                attr.dataType = _to_data_type_model(safe_merge_data_type(_data_type_payload(attr.dataType), new_attr_dt.model_dump(mode="json")))
                attr.dateModified = now
                attributes_changed += 1

            elif change_type == "PK_CHANGED":
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                attr = next((a for a in attributes if a.name == target_name), None)
                if not attr:
                    continue
                attr.isBusinessKey = bool(src_col.get("isPrimaryKey", False))
                attr.dateModified = now
                attributes_changed += 1

        entity.attributes = attributes

        write_model_entity(entity_rel_path, entity, solution_path)
        result.append(
            {
                "entityRelPath": entity_rel_path,
                "entityName": ent_entry.name,
                "attributesChanged": attributes_changed,
                "mappingsChanged": mappings_changed,
                "content": entity.model_dump(mode="json"),
            }
        )

    return result
