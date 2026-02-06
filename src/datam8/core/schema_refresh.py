from __future__ import annotations

import re
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
    list_base_entities,
    list_model_entities,
    write_model_entity,
)

DataType = dict[str, Any]


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
    return sanitize_data_type(dt)


def is_same_data_type(a: Any, b: Any) -> bool:
    left = sanitize_data_type(a)
    right = sanitize_data_type(b)
    return (
        left.get("type") == right.get("type")
        and left.get("charLen") == right.get("charLen")
        and left.get("precision") == right.get("precision")
        and left.get("scale") == right.get("scale")
    )


def safe_merge_data_type(current: Any, source: Any) -> DataType:
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


def _list_model_entities(solution_path: str | None) -> list[dict[str, Any]]:
    return [e.__dict__ for e in list_model_entities(solution_path)]


def find_data_source_usages(solution_path: str | None, data_source_name: str) -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []
    entities = _list_model_entities(solution_path)

    for ent in entities:
        rel_path = str(ent.get("relPath") or "").replace("\\", "/")
        content = ent.get("content") if isinstance(ent.get("content"), dict) else None
        sources = content.get("sources") if isinstance(content, dict) else None
        if not isinstance(sources, list):
            continue

        layer: str | None = None
        parts = [p for p in rel_path.split("/") if p]
        for p in parts:
            if re.match(r"^\d+-", p):
                layer = p
                break

        for idx, src in enumerate(sources):
            if not isinstance(src, dict):
                continue
            if src.get("dataSource") != data_source_name:
                continue
            usages.append(
                {
                    "entityRelPath": ent.get("relPath"),
                    "entityName": ent.get("name"),
                    "layer": layer,
                    "sourceIndex": idx,
                    "dataSource": src.get("dataSource"),
                    "sourceAlias": src.get("sourceAlias"),
                    "sourceLocation": src.get("sourceLocation"),
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

    ds_list = ds_entry.content.get("dataSources") if isinstance(ds_entry.content, dict) else None
    dst_list = dst_entry.content.get("dataSourceTypes") if isinstance(dst_entry.content, dict) else None
    if not isinstance(ds_list, list) or not isinstance(dst_list, list):
        return {"sourceMapping": [], "typeMapping": []}

    data_source = next((d for d in ds_list if isinstance(d, dict) and d.get("name") == data_source_name), None)
    if not isinstance(data_source, dict):
        return {"sourceMapping": [], "typeMapping": []}

    type_name = data_source.get("type") or data_source.get("dataSourceType")
    data_source_type = next((t for t in dst_list if isinstance(t, dict) and t.get("name") == type_name), None)

    source_mapping_raw = data_source.get("dataTypeMapping")
    source_mapping = [m for m in source_mapping_raw if isinstance(m, dict)] if isinstance(source_mapping_raw, list) else []

    type_mapping_raw = data_source_type.get("dataTypeMapping") if isinstance(data_source_type, dict) else None
    type_mapping = [m for m in type_mapping_raw if isinstance(m, dict)] if isinstance(type_mapping_raw, list) else []

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
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    entities = _list_model_entities(solution_path)
    entity_map = {str(e.get("relPath")): e for e in entities if isinstance(e, dict) and e.get("relPath")}

    for usage in usages:
        ent_entry = entity_map.get(usage.entity_rel_path)
        if not ent_entry:
            continue
        entity = ent_entry.get("content") if isinstance(ent_entry.get("content"), dict) else None
        if not isinstance(entity, dict):
            continue
        sources = entity.get("sources")
        if not isinstance(sources, list) or usage.source_index < 0 or usage.source_index >= len(sources):
            continue
        source = sources[usage.source_index]
        if not isinstance(source, dict):
            continue

        source_metadata = fetch_source_metadata(
            solution_path=solution_path,
            data_source_name=str(source.get("dataSource") or ""),
            source_location=str(source.get("sourceLocation") or ""),
            runtime_secrets=runtime_secrets,
        )

        mapping_raw = source.get("mapping")
        mapping = mapping_raw if isinstance(mapping_raw, list) else []
        attributes_raw = entity.get("attributes")
        attributes = attributes_raw if isinstance(attributes_raw, list) else []

        changes: list[dict[str, Any]] = []

        for src_col in source_metadata:
            src_name = src_col.get("name")
            if not isinstance(src_name, str):
                continue
            existing_map = next((m for m in mapping if isinstance(m, dict) and m.get("sourceName") == src_name), None)
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

            existing_type = normalize_data_type(existing_map.get("sourceDataType"))
            new_type = sanitize_data_type(src_col.get("dataType"))
            merged_type = safe_merge_data_type(existing_type, new_type)
            source_after = {**src_col, "dataType": merged_type}

            target_name = existing_map.get("targetName")
            attr = next((a for a in attributes if isinstance(a, dict) and a.get("name") == target_name), None)

            if not is_same_data_type(existing_type, merged_type):
                changes.append(
                    {
                        "changeType": "TYPE_CHANGED",
                        "columnName": src_name,
                        "sourceBefore": {"name": src_name, "dataType": existing_type, "isPrimaryKey": False},
                        "sourceAfter": source_after,
                        "entityAttributeName": attr.get("name") if isinstance(attr, dict) else None,
                        "entityAttributeBefore": attr,
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
                        "entityAttributeName": attr.get("name") if isinstance(attr, dict) else None,
                        "entityAttributeBefore": attr,
                        "applyToEntitySuggested": False,
                    }
                )

            if isinstance(attr, dict):
                attr_is_pk = bool(attr.get("isBusinessKey") or attr.get("isPrimaryKey") or False)
                if bool(src_col.get("isPrimaryKey", False)) != attr_is_pk:
                    changes.append(
                        {
                            "changeType": "PK_CHANGED",
                            "columnName": src_name,
                            "sourceBefore": {"name": src_name, "dataType": existing_type, "isPrimaryKey": attr_is_pk},
                            "sourceAfter": src_col,
                            "entityAttributeName": attr.get("name"),
                            "entityAttributeBefore": attr,
                            "applyToEntitySuggested": False,
                        }
                    )

        for map_item in mapping:
            if not isinstance(map_item, dict):
                continue
            src_name = map_item.get("sourceName")
            if not isinstance(src_name, str):
                continue
            exists = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == src_name), None)
            if exists:
                continue
            target_name = map_item.get("targetName")
            attr = next((a for a in attributes if isinstance(a, dict) and a.get("name") == target_name), None)
            if isinstance(attr, dict) and attr.get("dateDeleted"):
                continue
            changes.append(
                {
                    "changeType": "REMOVED_COLUMN",
                    "columnName": src_name,
                    "sourceBefore": {"name": src_name, "dataType": normalize_data_type(map_item.get("sourceDataType")), "isPrimaryKey": False},
                    "entityAttributeName": attr.get("name") if isinstance(attr, dict) else None,
                    "entityAttributeBefore": attr,
                    "applyToEntitySuggested": True,
                }
            )

        if changes:
            diffs.append(
                {
                    "entityRelPath": usage.entity_rel_path,
                    "entityName": ent_entry.get("name"),
                    "sourceIndex": usage.source_index,
                    "dataSource": source.get("dataSource"),
                    "sourceAlias": source.get("sourceAlias"),
                    "sourceLocation": source.get("sourceLocation"),
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
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    entities = _list_model_entities(solution_path)
    entity_map = {str(e.get("relPath")): e for e in entities if isinstance(e, dict) and e.get("relPath")}
    mapping_cache: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for diff_item in diffs:
        entity_rel_path = diff_item.get("entityRelPath")
        source_index = diff_item.get("sourceIndex")
        if not isinstance(entity_rel_path, str) or not isinstance(source_index, int):
            continue

        ent_entry = entity_map.get(entity_rel_path)
        if not ent_entry:
            continue

        entity = ent_entry.get("content") if isinstance(ent_entry.get("content"), dict) else None
        if not isinstance(entity, dict):
            continue
        sources = entity.get("sources")
        if not isinstance(sources, list) or source_index < 0 or source_index >= len(sources):
            continue
        source = sources[source_index]
        if not isinstance(source, dict):
            continue

        ds_name = str(source.get("dataSource") or "")
        source_location = str(source.get("sourceLocation") or "")

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
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        new_mapping: list[dict[str, Any]] = []
        current_mapping_raw = source.get("mapping")
        current_mapping = current_mapping_raw if isinstance(current_mapping_raw, list) else []

        for src_col in source_metadata:
            if not isinstance(src_col, dict) or not isinstance(src_col.get("name"), str):
                continue
            src_name = src_col["name"]
            existing_map = next((m for m in current_mapping if isinstance(m, dict) and m.get("sourceName") == src_name), None)
            if existing_map:
                existing_type = normalize_data_type(existing_map.get("sourceDataType"))
                new_type = sanitize_data_type(src_col.get("dataType"))
                merged_type = safe_merge_data_type(existing_type, new_type)
                mapping_changed = (not is_same_data_type(existing_type, merged_type)) or bool(existing_type.get("nullable")) != bool(merged_type.get("nullable"))
                sanitized_existing = {**existing_map, "sourceDataType": merged_type}
                if mapping_changed:
                    mappings_changed += 1
                new_mapping.append(sanitized_existing)
            else:
                mappings_changed += 1
                new_mapping.append(
                    {
                        "targetName": src_name,
                        "sourceName": src_name,
                        "sourceDataType": sanitize_data_type(src_col.get("dataType")),
                        "properties": [],
                    }
                )

        if len(new_mapping) != len(current_mapping):
            mappings_changed += 1
        source["mapping"] = new_mapping

        # Apply to entity schema (selected changes only)
        changes_raw = diff_item.get("changes")
        changes = changes_raw if isinstance(changes_raw, list) else []
        if not isinstance(entity.get("attributes"), list):
            entity["attributes"] = []

        for ch in changes:
            if not isinstance(ch, dict) or not ch.get("applyToEntity"):
                continue
            column_name = ch.get("columnName")
            change_type = ch.get("changeType")
            if not isinstance(column_name, str) or not isinstance(change_type, str):
                continue
            map_entry = next((m for m in new_mapping if isinstance(m, dict) and m.get("sourceName") == column_name), None)
            target_name = (map_entry.get("targetName") if isinstance(map_entry, dict) else None) or column_name

            if change_type == "NEW_COLUMN":
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                source_type_simple = sanitize_data_type(src_col.get("dataType")).get("type")
                target_type_name = _resolve_target_type(mappings, str(source_type_simple or "string"))
                new_attr_dt = sanitize_data_type({**sanitize_data_type(src_col.get("dataType")), "type": target_type_name})
                attr = next((a for a in entity["attributes"] if isinstance(a, dict) and a.get("name") == target_name), None)
                if isinstance(attr, dict):
                    if attr.get("dateDeleted"):
                        attr.pop("dateDeleted", None)
                        attr["dateModified"] = now
                        attr["dataType"] = safe_merge_data_type(normalize_data_type(attr.get("dataType")), new_attr_dt)
                        attributes_changed += 1
                else:
                    max_ordinal = 0
                    for a in entity["attributes"]:
                        if isinstance(a, dict) and isinstance(a.get("ordinalNumber"), int):
                            max_ordinal = max(max_ordinal, a.get("ordinalNumber") or 0)
                    entity["attributes"].append(
                        {
                            "name": target_name,
                            "attributeType": "Physical",
                            "ordinalNumber": max_ordinal + 10,
                            "dataType": new_attr_dt,
                            "dateAdded": now,
                        }
                    )
                    attributes_changed += 1

            elif change_type == "REMOVED_COLUMN":
                attr = next((a for a in entity["attributes"] if isinstance(a, dict) and a.get("name") == target_name), None)
                if not attr and isinstance(ch.get("entityAttributeName"), str):
                    ea = ch.get("entityAttributeName")
                    attr = next((a for a in entity["attributes"] if isinstance(a, dict) and a.get("name") == ea), None)
                if isinstance(attr, dict):
                    attr["dateDeleted"] = now
                    attributes_changed += 1

            elif change_type in {"TYPE_CHANGED", "NULLABILITY_CHANGED"}:
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                attr = next((a for a in entity["attributes"] if isinstance(a, dict) and a.get("name") == target_name), None)
                if not isinstance(attr, dict):
                    continue
                source_type_simple = sanitize_data_type(src_col.get("dataType")).get("type")
                target_type_name = _resolve_target_type(mappings, str(source_type_simple or "string"))
                new_attr_dt = sanitize_data_type({**sanitize_data_type(src_col.get("dataType")), "type": target_type_name})
                attr["dataType"] = safe_merge_data_type(normalize_data_type(attr.get("dataType")), new_attr_dt)
                attr["dateModified"] = now
                attributes_changed += 1

            elif change_type == "PK_CHANGED":
                src_col = next((c for c in source_metadata if isinstance(c, dict) and c.get("name") == column_name), None)
                if not src_col:
                    continue
                attr = next((a for a in entity["attributes"] if isinstance(a, dict) and a.get("name") == target_name), None)
                if not isinstance(attr, dict):
                    continue
                attr["isBusinessKey"] = bool(src_col.get("isPrimaryKey", False))
                attr["dateModified"] = now
                attributes_changed += 1

        # Persist entity
        write_model_entity(entity_rel_path, entity, solution_path)
        result.append(
            {
                "entityRelPath": entity_rel_path,
                "entityName": ent_entry.get("name"),
                "attributesChanged": attributes_changed,
                "mappingsChanged": mappings_changed,
                "content": entity,
            }
        )

    return result
