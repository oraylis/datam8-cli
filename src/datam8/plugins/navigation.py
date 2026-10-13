"""Adapt legacy navigation rows once, before they reach source UI consumers."""

from typing import Any

from datam8.errors import Datam8ValidationError


def normalize_source_item(item: dict[str, Any], parent: str | None = None) -> dict[str, Any]:
    schema = str(item.get("schema") or "")
    container = str(item.get("container") or "")
    name = str(item.get("name") or item.get("object") or schema or container)
    kind = str(item.get("type") or "").upper()
    has_object = bool(item.get("name") or item.get("object"))
    if not kind:
        kind = (
            "SCHEMA"
            if schema and not has_object
            else "CONTAINER"
            if container and not has_object
            else "OBJECT"
        )
    location = item.get("sourceLocation")
    if location is None:
        if kind in {"SCHEMA", "CONTAINER"}:
            location = container or schema or name
        elif container:
            location = f"{container}@{name}"
        elif kind in {"FILE", "DIRECTORY"}:
            location = f"{parent.rstrip('/')}/{name}" if parent else name
        elif schema:
            location = f"[{schema.replace(']', ']]')}].[{name.replace(']', ']]')}]"
        else:
            location = name
    if not name.strip() or not isinstance(location, str) or not location.strip():
        raise Datam8ValidationError(message="Source navigation requires a name and sourceLocation")
    result = {**item, "name": name, "type": kind, "sourceLocation": location}
    if item.get("schema") is not None:
        result["schema"] = schema
    return result
