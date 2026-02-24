from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from datam8_model.model import Locator


def _norm_posix(path: str) -> str:
    return str(PurePosixPath((path or "").replace("\\", "/"))).replace("\\", "/")


def locator_to_string(locator: Locator) -> str:
    parts: list[str] = [locator.entityType]
    parts.extend(str(p) for p in locator.folders)
    if locator.entityName:
        parts.append(locator.entityName)
    return "/" + "/".join(parts)


def locator_sort_key(locator: Locator) -> str:
    return locator_to_string(locator)


def relpath_to_model_locator(*, rel_path: str, model_path: str) -> Locator:
    rel = _norm_posix(rel_path).lstrip("/")
    model_root = _norm_posix(model_path).strip("/")

    if model_root and rel.startswith(f"{model_root}/"):
        tail = rel[len(model_root) + 1 :]
    elif rel == model_root:
        tail = ""
    else:
        tail = rel

    tail = tail.removesuffix(".json")
    parts = [p for p in tail.split("/") if p]
    if not parts:
        raise ValueError(f"Cannot derive model locator from relPath '{rel_path}'.")

    return Locator(entityType="modelEntities", folders=parts[:-1], entityName=parts[-1])


def model_locator_to_relpath(*, locator: Locator, model_path: str) -> str:
    if locator.entityType != "modelEntities":
        raise ValueError(f"Expected locator.entityType='modelEntities', got '{locator.entityType}'.")
    if not locator.entityName:
        raise ValueError("Model entity locator requires entityName.")

    model_root = _norm_posix(model_path).strip("/")
    parts = [model_root] if model_root else []
    parts.extend(str(p) for p in locator.folders)
    parts.append(locator.entityName)
    return "/".join(parts) + ".json"


def folder_path_to_locator(folder_path: str) -> Locator:
    norm = _norm_posix(folder_path).strip("/")
    if not norm:
        return Locator(entityType="folders", folders=[], entityName=None)
    parts = [p for p in norm.split("/") if p]
    return Locator(entityType="folders", folders=parts[:-1], entityName=parts[-1])


def folder_locator_to_folder_path(locator: Locator) -> str:
    if locator.entityType != "folders":
        raise ValueError(f"Expected locator.entityType='folders', got '{locator.entityType}'.")
    parts = [str(p) for p in locator.folders]
    if locator.entityName:
        parts.append(locator.entityName)
    return "/".join(parts)


def parse_locator(value: Any) -> Locator:
    if isinstance(value, Locator):
        return value
    if isinstance(value, dict):
        return Locator.model_validate(value)
    if not isinstance(value, str):
        raise ValueError(f"Unsupported locator type: {type(value)}")

    raw = value.strip()
    if not raw:
        raise ValueError("Empty locator.")

    if raw.startswith("{"):
        parsed = json.loads(raw)
        return Locator.model_validate(parsed)

    s = raw.lstrip("/")
    s = s.removesuffix(".json")
    parts = [p for p in s.split("/") if p]
    if not parts:
        raise ValueError("Empty locator path.")

    # Canonical locator path representation:
    # /modelEntities/<folders...>/<entityName>
    # /folders/<folders...>/<folderName?>
    first = parts[0]
    if first in {"modelEntities", "folders"}:
        rest = parts[1:]
        if not rest:
            return Locator(entityType=first, folders=[], entityName=None)
        return Locator(entityType=first, folders=rest[:-1], entityName=rest[-1])

    raise ValueError("Locator must be '/modelEntities/...', '/folders/...', JSON object, or dict payload.")
