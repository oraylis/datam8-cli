from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from datam8.core.atomic import atomic_write_json
from datam8.core.errors import Datam8ValidationError
from datam8.core.solution_files import iter_solution_json_files


@dataclass(frozen=True)
class RefactorChange:
    file: str
    changed: bool
    changes: int


def refactor_keys(
    *,
    solution_path: str | None,
    renames: dict[str, str],
    apply: bool,
) -> dict[str, Any]:
    if not renames:
        raise Datam8ValidationError(message="No renames provided.", details=None)
    results: list[RefactorChange] = []
    changed_files: list[str] = []

    for p in iter_solution_json_files(solution_path):
        raw = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            continue
        next_data, changes = _rename_keys(data, renames)
        if changes:
            changed_files.append(str(p))
            if apply:
                atomic_write_json(p, next_data, indent=4)
        results.append(RefactorChange(file=str(p), changed=changes > 0, changes=changes))

    return {
        "changedFiles": changed_files,
        "updatedFiles": len(changed_files),
        "totalEdits": sum(r.changes for r in results),
        "results": [r.__dict__ for r in results],
    }


def refactor_values(
    *,
    solution_path: str | None,
    old: str,
    new: str,
    apply: bool,
    key: str | None = None,
) -> dict[str, Any]:
    if old is None or new is None or old == "":
        raise Datam8ValidationError(message="Invalid value refactor.", details={"old": old, "new": new})
    results: list[RefactorChange] = []
    changed_files: list[str] = []

    for p in iter_solution_json_files(solution_path):
        raw = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            continue
        next_data, changes = _replace_values(data, old=old, new=new, key=key)
        if changes:
            changed_files.append(str(p))
            if apply:
                atomic_write_json(p, next_data, indent=4)
        results.append(RefactorChange(file=str(p), changed=changes > 0, changes=changes))

    return {
        "changedFiles": changed_files,
        "updatedFiles": len(changed_files),
        "totalEdits": sum(r.changes for r in results),
        "results": [r.__dict__ for r in results],
    }


def refactor_entity_id(
    *,
    solution_path: str | None,
    old: int,
    new: int,
    apply: bool,
    reference_keys: list[str] | None = None,
) -> dict[str, Any]:
    if old == new:
        raise Datam8ValidationError(message="old and new ids are identical.", details={"id": old})
    keys = set(reference_keys or ["entityId", "sourceEntityId", "targetEntityId", "refEntityId"])
    keys.add("id")
    results: list[RefactorChange] = []
    changed_files: list[str] = []

    for p in iter_solution_json_files(solution_path):
        raw = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            continue
        next_data, changes = _replace_int_values_for_keys(data, keys=keys, old=old, new=new)
        if changes:
            changed_files.append(str(p))
            if apply:
                atomic_write_json(p, next_data, indent=4)
        results.append(RefactorChange(file=str(p), changed=changes > 0, changes=changes))

    return {
        "changedFiles": changed_files,
        "updatedFiles": len(changed_files),
        "totalEdits": sum(r.changes for r in results),
        "results": [r.__dict__ for r in results],
    }


def _rename_keys(node: Any, renames: dict[str, str]) -> tuple[Any, int]:
    if isinstance(node, list):
        changes = 0
        next_list = []
        for item in node:
            v, c = _rename_keys(item, renames)
            changes += c
            next_list.append(v)
        return next_list, changes
    if isinstance(node, dict):
        changes = 0
        next_dict: dict[str, Any] = {}
        for k, v in node.items():
            nk = renames.get(k) or k
            if nk != k:
                changes += 1
            vv, c = _rename_keys(v, renames)
            changes += c
            next_dict[nk] = vv
        return next_dict, changes
    return node, 0


def _replace_values(node: Any, *, old: str, new: str, key: str | None) -> tuple[Any, int]:
    if isinstance(node, list):
        changes = 0
        next_list = []
        for item in node:
            v, c = _replace_values(item, old=old, new=new, key=key)
            changes += c
            next_list.append(v)
        return next_list, changes
    if isinstance(node, dict):
        changes = 0
        next_dict: dict[str, Any] = {}
        for k, v in node.items():
            if key is not None and k == key and isinstance(v, str) and v == old:
                next_dict[k] = new
                changes += 1
                continue
            vv, c = _replace_values(v, old=old, new=new, key=key)
            changes += c
            next_dict[k] = vv
        return next_dict, changes
    if key is None and isinstance(node, str) and node == old:
        return new, 1
    return node, 0


def _replace_int_values_for_keys(node: Any, *, keys: set[str], old: int, new: int) -> tuple[Any, int]:
    if isinstance(node, list):
        changes = 0
        next_list = []
        for item in node:
            v, c = _replace_int_values_for_keys(item, keys=keys, old=old, new=new)
            changes += c
            next_list.append(v)
        return next_list, changes
    if isinstance(node, dict):
        changes = 0
        next_dict: dict[str, Any] = {}
        for k, v in node.items():
            if k in keys and isinstance(v, int) and v == old:
                next_dict[k] = new
                changes += 1
                continue
            vv, c = _replace_int_values_for_keys(v, keys=keys, old=old, new=new)
            changes += c
            next_dict[k] = vv
        return next_dict, changes
    return node, 0
