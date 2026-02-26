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
from copy import deepcopy
from typing import Any

from datam8.core.migration_v1_to_v2_config import (
    ZONE_ENTRY_BY_NAME,
    ZONE_MODEL_ORDER,
    default_generator_targets,
)


def compose_description(primary: Any, secondary: Any) -> str:
    first = primary.strip() if isinstance(primary, str) and primary.strip() else ""
    second = secondary.strip() if isinstance(secondary, str) and secondary.strip() else ""
    if first and second:
        return f"{first}\n{second}"
    return first or second or ""


def normalize_has_unit(value: Any, is_unit: Any, warnings: list[str], context: str) -> str | None:
    candidate = value
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = is_unit

    if candidate is None:
        return None
    if not isinstance(candidate, str):
        warnings.append(f"{context}: invalid hasUnit value {candidate!r}; omitted.")
        return None

    raw = candidate.strip()
    if not raw:
        return None

    if raw in {"NoUnit", "Physical", "Currency"}:
        return raw

    normalized = re.sub(r"[^a-z0-9]+", "", raw.lower())
    if normalized in {"nounit", "unitfree", "none", "null", "na"}:
        return "NoUnit"
    if normalized in {"physical"}:
        return "Physical"
    if normalized in {"currency"}:
        return "Currency"

    warnings.append(f"{context}: unsupported hasUnit value '{raw}'; omitted.")
    return None


def convert_base_attribute_types(v1_attribute_types: Any, warnings: list[str]) -> dict[str, Any]:
    converted_attribute_types = []
    for a in (v1_attribute_types or {}).get("items", []) if isinstance(v1_attribute_types, dict) else []:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        converted_attribute_types.append(
            {
                "name": name,
                "displayName": a.get("displayName") if isinstance(a.get("displayName"), str) else name,
                "description": compose_description(a.get("purpose"), a.get("explanation") or a.get("description")),
                "defaultType": a.get("defaultType"),
                "defaultLength": a.get("defaultLength"),
                "defaultPrecision": a.get("defaultPrecision"),
                "defaultScale": a.get("defaultScale"),
                "hasUnit": normalize_has_unit(
                    a.get("hasUnit"),
                    a.get("isUnit"),
                    warnings,
                    f"Base/AttributeTypes.json:{name}",
                ),
                "canBeInRelation": a.get("canBeInRelation"),
                "isDefaultProperty": a.get("isDefaultProperty"),
            }
        )

    return {
        "type": "attributeTypes",
        "attributeTypes": converted_attribute_types,
    }


def convert_base_data_products(v1_data_products: Any) -> dict[str, Any]:
    out_data_products = {"type": "dataProducts", "dataProducts": []}
    for p in (v1_data_products or {}).get("items", []) if isinstance(v1_data_products, dict) else []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        modules = []
        for m in p.get("module", []) if isinstance(p.get("module"), list) else []:
            if not isinstance(m, dict):
                continue
            mname = m.get("name")
            if not isinstance(mname, str) or not mname.strip():
                continue
            modules.append(
                {
                    "name": mname,
                    "displayName": m.get("displayName") if isinstance(m.get("displayName"), str) else mname,
                    "description": compose_description(m.get("purpose"), m.get("explanation")),
                }
            )
        out_data_products["dataProducts"].append(
            {
                "name": name,
                "displayName": p.get("displayName") if isinstance(p.get("displayName"), str) else name,
                "description": compose_description(p.get("purpose"), p.get("explanation")),
                "dataModules": modules,
            }
        )
    return out_data_products


def convert_base_data_sources(v1_data_sources: Any) -> dict[str, Any]:
    out_data_sources = {"type": "dataSources", "dataSources": []}
    for s in (v1_data_sources or {}).get("items", []) if isinstance(v1_data_sources, dict) else []:
        if not isinstance(s, dict):
            continue
        name = s.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        out_data_sources["dataSources"].append(
            {
                "name": name,
                "displayName": s.get("displayName") if isinstance(s.get("displayName"), str) else name,
                "description": compose_description(s.get("purpose"), s.get("explanation")),
                "type": s.get("type"),
                "connectionString": s.get("connectionString"),
                "dataTypeMapping": s.get("dataTypeMapping") if isinstance(s.get("dataTypeMapping"), list) else None,
                "extendedProperties": (
                    s.get("extendedProperties")
                    if isinstance(s.get("extendedProperties"), dict)
                    else (s.get("ExtendedProperties") if isinstance(s.get("ExtendedProperties"), dict) else None)
                ),
            }
        )
    return out_data_sources


def convert_base_data_types(v1_data_types: Any, warnings: list[str]) -> dict[str, Any]:
    converted_data_types = []
    for t in (v1_data_types or {}).get("items", []) if isinstance(v1_data_types, dict) else []:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        targets: dict[str, str] = {}
        parquet = t.get("parquetType")
        sql_type = t.get("sqlType")
        if isinstance(parquet, str) and parquet.strip():
            targets["databricks"] = parquet.strip()
        if isinstance(sql_type, str) and sql_type.strip():
            targets["sqlserver"] = sql_type.strip()
        if not targets:
            targets["databricks"] = name.strip()
            warnings.append(f"Base/DataTypes.json: '{name}' missing parquetType/sqlType; using fallback targets.")
        converted_data_types.append(
            {
                "name": name,
                "displayName": t.get("displayName") if isinstance(t.get("displayName"), str) else name,
                "description": compose_description(t.get("purpose"), t.get("explanation") or t.get("description")),
                "hasCharLen": bool(t.get("hasCharLen", False)),
                "hasPrecision": bool(t.get("hasPrecision", False)),
                "hasScale": bool(t.get("hasScale", False)),
                "targets": targets,
            }
        )

    return {"type": "dataTypes", "dataTypes": converted_data_types}


def build_data_source_types(out_data_sources: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ds in out_data_sources.get("dataSources") or []:
        t = ds.get("type")
        type_name = t.strip() if isinstance(t, str) and t.strip() else "Unknown"
        by_type.setdefault(type_name, []).append(ds)

    out_data_source_types = {"type": "dataSourceTypes", "dataSourceTypes": []}
    for type_name, sources in by_type.items():
        mappings: list[dict[str, str]] = []
        for s in sources:
            for row in s.get("dataTypeMapping") or []:
                if isinstance(row, dict) and isinstance(row.get("sourceType"), str) and isinstance(row.get("targetType"), str):
                    mappings.append({"sourceType": row["sourceType"], "targetType": row["targetType"]})
        uniq: dict[str, dict[str, str]] = {}
        for mapping in mappings:
            uniq[f"{mapping['sourceType']}::{mapping['targetType']}"] = mapping
        data_type_mapping = list(uniq.values())
        if not data_type_mapping:
            warnings.append(f"Base/DataSourceTypes.json: '{type_name}' has no dataTypeMapping; generated fallback mapping.")
            data_type_mapping = [{"sourceType": "string", "targetType": "string"}]
        out_data_source_types["dataSourceTypes"].append(
            {
                "name": type_name,
                "displayName": type_name,
                "description": "",
                "dataTypeMapping": data_type_mapping,
            }
        )

    return out_data_source_types


def build_zone_entries(present_zones: set[str]) -> dict[str, Any]:
    out: list[dict[str, str]] = []
    for zone in ("raw", *ZONE_MODEL_ORDER):
        if zone in present_zones and zone in ZONE_ENTRY_BY_NAME:
            out.append(deepcopy(ZONE_ENTRY_BY_NAME[zone]))
    if not out:
        out = [deepcopy(ZONE_ENTRY_BY_NAME["stage"])]
    return {"type": "zones", "zones": out}


def build_generator_targets(target_names: list[str]) -> list[dict[str, Any]]:
    generator_targets: list[dict[str, Any]] = []
    for raw_name in target_names:
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if not name:
            continue
        if name.startswith(".") or name.startswith("__"):
            continue
        generator_targets.append(
            {
                "name": name,
                "isDefault": False,
                "sourcePath": f"Generate/{name}",
                "outputPath": f"Output/{name}/generated",
            }
        )

    if not generator_targets:
        return default_generator_targets()

    generator_targets[0]["isDefault"] = True
    return generator_targets
