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

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from datam8_model_v1 import models as v1


class V1ParseError(Exception):
    def __init__(self, message: str, *, path: Path | None = None, cause: Exception | None = None):
        details = f"{path}: {message}" if path else message
        super().__init__(details)
        self.path = path
        self.cause = cause


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise V1ParseError("Failed to read JSON.", path=path, cause=e) from e


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if isinstance(value, str):
        txt = value.strip()
        return txt if txt else None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        try:
            return int(float(txt))
        except Exception:
            return None
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        txt = value.strip().lower()
        if txt in {"1", "true", "yes", "y"}:
            return True
        if txt in {"0", "false", "no", "n"}:
            return False
    return None


def _normalize_parameter(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "name": _as_str(row.get("name")),
        "value": row.get("value"),
        "custom": row.get("custom"),
    }


def _normalize_mapping_item(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "name": _as_str(row.get("name")),
        "sourceName": _as_str(row.get("sourceName")),
        "sourceComputation": _as_str(row.get("sourceComputation")),
        "source": _as_str(row.get("source")),
        "target": _as_str(row.get("target")),
    }


def _normalize_relationship_field(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "dm8lAttr": _as_str(row.get("dm8lAttr")),
        "dm8lKeyAttr": _as_str(row.get("dm8lKeyAttr")),
    }


def _normalize_relationship(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "dm8lKey": _as_str(row.get("dm8lKey")),
        "role": _as_str(row.get("role")),
        "fields": [_normalize_relationship_field(x) for x in _as_list(row.get("fields"))],
    }


def _normalize_attribute(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "name": _as_str(row.get("name")),
        "displayName": _as_str(row.get("displayName")),
        "purpose": _as_str(row.get("purpose")),
        "explanation": _as_str(row.get("explanation")),
        "attributeType": _as_str(row.get("attributeType")),
        "dataType": _as_str(row.get("dataType")),
        "type": _as_str(row.get("type")),
        "businessKeyNo": _as_int(row.get("businessKeyNo")),
        "tags": [x.strip() for x in _as_list(row.get("tags")) if isinstance(x, str) and x.strip()],
        "parameter": [_normalize_parameter(x) for x in _as_list(row.get("parameter"))],
        "refactorNames": [x for x in _as_list(row.get("refactorNames")) if isinstance(x, str)],
        "nullable": _as_bool(row.get("nullable")),
        "charLength": _as_int(row.get("charLength")),
        "charLen": _as_int(row.get("charLen")),
        "precision": _as_int(row.get("precision")),
        "scale": _as_int(row.get("scale")),
        "history": _as_str(row.get("history")),
        "dateModified": _as_str(row.get("dateModified")),
    }


def _normalize_entity(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "dataProduct": _as_str(row.get("dataProduct")),
        "dataModule": _as_str(row.get("dataModule")),
        "name": _as_str(row.get("name")),
        "displayName": _as_str(row.get("displayName")),
        "purpose": _as_str(row.get("purpose")),
        "explanation": _as_str(row.get("explanation")),
        "parameters": [_normalize_parameter(x) for x in _as_list(row.get("parameters"))],
        "tags": [x.strip() for x in _as_list(row.get("tags")) if isinstance(x, str) and x.strip()],
        "attribute": [_normalize_attribute(x) for x in _as_list(row.get("attribute"))],
        "relationship": [_normalize_relationship(x) for x in _as_list(row.get("relationship"))],
    }


def _normalize_source(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "dm8l": _as_str(row.get("dm8l")),
        "mapping": [_normalize_mapping_item(x) for x in _as_list(row.get("mapping"))],
    }


def _normalize_function(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "dataSource": _as_str(row.get("dataSource")),
        "sourceLocation": _as_str(row.get("sourceLocation")),
        "source": [_normalize_source(x) for x in _as_list(row.get("source"))],
        "attributeMapping": [_normalize_mapping_item(x) for x in _as_list(row.get("attributeMapping"))],
        "name": _as_str(row.get("name")),
    }


def _validate(model_cls: Any, payload: dict[str, Any], path: Path) -> Any:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as e:
        raise V1ParseError("V1 schema validation failed.", path=path, cause=e) from e


def parse_solution_file(path: Path) -> v1.Solution:
    raw = _as_dict(_read_json(path))
    payload = {
        "basePath": _as_str(raw.get("basePath")),
        "rawPath": _as_str(raw.get("rawPath")),
        "stagingPath": _as_str(raw.get("stagingPath")),
        "corePath": _as_str(raw.get("corePath")),
        "curatedPath": _as_str(raw.get("curatedPath")),
        "generatePath": _as_str(raw.get("generatePath")),
        "diagramPath": _as_str(raw.get("diagramPath")),
        "outputPath": _as_str(raw.get("outputPath")),
        "AreaTypes": _as_dict(raw.get("AreaTypes")) or None,
    }
    return _validate(v1.Solution, payload, path)


def parse_base_file(path: Path, file_name: str) -> v1.BaseEntitiesType:
    raw = _as_dict(_read_json(path))
    items = _as_list(raw.get("items"))

    if file_name == "AttributeTypes.json":
        payload = {
            "type": _as_str(raw.get("type")),
            "items": [
                {
                    "name": _as_str(_as_dict(x).get("name")),
                    "displayName": _as_str(_as_dict(x).get("displayName")),
                    "purpose": _as_str(_as_dict(x).get("purpose")),
                    "explanation": _as_str(_as_dict(x).get("explanation")),
                    "description": _as_str(_as_dict(x).get("description")),
                    "defaultType": _as_str(_as_dict(x).get("defaultType")),
                    "defaultLength": _as_int(_as_dict(x).get("defaultLength")),
                    "defaultPrecision": _as_int(_as_dict(x).get("defaultPrecision")),
                    "defaultScale": _as_int(_as_dict(x).get("defaultScale")),
                    "hasUnit": _as_str(_as_dict(x).get("hasUnit")),
                    "isUnit": _as_str(_as_dict(x).get("isUnit")),
                    "canBeInRelation": _as_bool(_as_dict(x).get("canBeInRelation")),
                    "isDefaultProperty": _as_bool(_as_dict(x).get("isDefaultProperty")),
                }
                for x in items
            ],
        }
        return _validate(v1.AttributeTypes, payload, path)

    if file_name == "DataProducts.json":
        payload = {
            "type": _as_str(raw.get("type")),
            "items": [
                {
                    "name": _as_str(_as_dict(x).get("name")),
                    "displayName": _as_str(_as_dict(x).get("displayName")),
                    "purpose": _as_str(_as_dict(x).get("purpose")),
                    "explanation": _as_str(_as_dict(x).get("explanation")),
                    "module": [
                        {
                            "name": _as_str(_as_dict(m).get("name")),
                            "displayName": _as_str(_as_dict(m).get("displayName")),
                            "purpose": _as_str(_as_dict(m).get("purpose")),
                            "explanation": _as_str(_as_dict(m).get("explanation")),
                        }
                        for m in _as_list(_as_dict(x).get("module"))
                    ],
                }
                for x in items
            ],
        }
        return _validate(v1.DataProducts, payload, path)

    if file_name == "DataSources.json":
        payload = {
            "type": _as_str(raw.get("type")),
            "items": [
                {
                    "name": _as_str(_as_dict(x).get("name")),
                    "displayName": _as_str(_as_dict(x).get("displayName")),
                    "purpose": _as_str(_as_dict(x).get("purpose")),
                    "explanation": _as_str(_as_dict(x).get("explanation")),
                    "type": _as_str(_as_dict(x).get("type")),
                    "connectionString": _as_str(_as_dict(x).get("connectionString")),
                    "dataTypeMapping": [
                        {
                            "sourceType": _as_str(_as_dict(m).get("sourceType")),
                            "targetType": _as_str(_as_dict(m).get("targetType")),
                        }
                        for m in _as_list(_as_dict(x).get("dataTypeMapping"))
                    ],
                    "extendedProperties": (
                        _as_dict(_as_dict(x).get("ExtendedProperties"))
                        or _as_dict(_as_dict(x).get("extendedProperties"))
                        or None
                    ),
                }
                for x in items
            ],
        }
        return _validate(v1.DataSources, payload, path)

    if file_name == "DataTypes.json":
        payload = {
            "type": _as_str(raw.get("type")),
            "items": [
                {
                    "name": _as_str(_as_dict(x).get("name")),
                    "displayName": _as_str(_as_dict(x).get("displayName")),
                    "purpose": _as_str(_as_dict(x).get("purpose")),
                    "explanation": _as_str(_as_dict(x).get("explanation")),
                    "description": _as_str(_as_dict(x).get("description")),
                    "hasCharLen": _as_bool(_as_dict(x).get("hasCharLen")),
                    "hasPrecision": _as_bool(_as_dict(x).get("hasPrecision")),
                    "hasScale": _as_bool(_as_dict(x).get("hasScale")),
                    "parquetType": _as_str(_as_dict(x).get("parquetType")),
                    "sqlType": _as_str(_as_dict(x).get("sqlType")),
                }
                for x in items
            ],
        }
        return _validate(v1.DataTypes, payload, path)

    raise V1ParseError(f"Unsupported base file '{file_name}'.", path=path)


def parse_model_file(path: Path) -> v1.ModelEntitiesType:
    raw = _as_dict(_read_json(path))
    kind = (_as_str(raw.get("type")) or "").lower()
    payload = {
        "type": kind,
        "entity": _normalize_entity(raw.get("entity")),
    }

    if kind == "curated":
        payload["function"] = [_normalize_function(x) for x in _as_list(raw.get("function"))]
        return _validate(v1.CuratedModelEntry, payload, path)

    payload["function"] = _normalize_function(raw.get("function"))
    if kind == "raw":
        return _validate(v1.RawModelEntry, payload, path)
    if kind == "stage":
        return _validate(v1.StageModelEntry, payload, path)
    if kind == "core":
        return _validate(v1.CoreModelEntry, payload, path)

    raise V1ParseError(f"Unsupported model type '{kind}'.", path=path)
