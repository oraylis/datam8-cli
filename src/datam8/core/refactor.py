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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from datam8.core.atomic import atomic_write_json
from datam8.core.errors import Datam8ValidationError
from datam8.core.solution_index import iter_solution_json_files


class RefactorChange(BaseModel):
    """Per-file refactor summary."""

    file: str
    changed: bool
    changes: int


def _iter_json_documents(solution_path: str | None) -> list[tuple[Path, Any]]:
    """Scan solution JSON files once and return parseable documents."""
    documents: list[tuple[Path, Any]] = []
    for path in iter_solution_json_files(solution_path):
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            continue
        documents.append((path, data))
    return documents


def _run_refactor(
    *,
    solution_path: str | None,
    apply: bool,
    transform: Callable[[Any], tuple[Any, int]],
) -> dict[str, Any]:
    """Execute one refactor transform across all solution JSON documents."""
    results: list[RefactorChange] = []
    changed_files: list[str] = []
    for path, data in _iter_json_documents(solution_path):
        next_data, changes = transform(data)
        if changes:
            changed_files.append(str(path))
            if apply:
                atomic_write_json(path, next_data, indent=4)
        results.append(RefactorChange(file=str(path), changed=changes > 0, changes=changes))

    return {
        "changedFiles": changed_files,
        "updatedFiles": len(changed_files),
        "totalEdits": sum(result.changes for result in results),
        "results": [result.model_dump() for result in results],
    }


def refactor_keys(
    *,
    solution_path: str | None,
    renames: dict[str, str],
    apply: bool,
) -> dict[str, Any]:
    """Rename JSON object keys across all solution JSON files.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    renames : dict[str, str]
        Mapping from old key names to new key names.
    apply : bool
        When `True`, writes updated files; otherwise runs as dry-run.

    Returns
    -------
    dict[str, Any]
        Refactor summary including changed files and edit counts.

    Raises
    ------
    Datam8ValidationError
        If no key rename mappings are provided."""
    if not renames:
        raise Datam8ValidationError(message="No renames provided.", details=None)
    return _run_refactor(solution_path=solution_path, apply=apply, transform=lambda node: _rename_keys(node, renames))


def refactor_values(
    *,
    solution_path: str | None,
    old: str,
    new: str,
    apply: bool,
    key: str | None = None,
) -> dict[str, Any]:
    """Replace string values across solution JSON files.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    old : str
        Value to replace.
    new : str
        Replacement value.
    apply : bool
        When `True`, writes updated files; otherwise runs as dry-run.
    key : str | None
        Optional key restriction; when set, only matching keys are replaced.

    Returns
    -------
    dict[str, Any]
        Refactor summary including changed files and edit counts.

    Raises
    ------
    Datam8ValidationError
        If input values are invalid."""
    if old is None or new is None or old == "":
        raise Datam8ValidationError(message="Invalid value refactor.", details={"old": old, "new": new})
    return _run_refactor(
        solution_path=solution_path,
        apply=apply,
        transform=lambda node: _replace_values(node, old=old, new=new, key=key),
    )


def refactor_entity_id(
    *,
    solution_path: str | None,
    old: int,
    new: int,
    apply: bool,
    reference_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Replace entity-id references across solution JSON files.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    old : int
        Existing entity id to replace.
    new : int
        New entity id.
    apply : bool
        When `True`, writes updated files; otherwise runs as dry-run.
    reference_keys : list[str] | None
        Optional additional key names to treat as id references.

    Returns
    -------
    dict[str, Any]
        Refactor summary including changed files and edit counts.

    Raises
    ------
    Datam8ValidationError
        If `old` and `new` are identical."""
    if old == new:
        raise Datam8ValidationError(message="old and new ids are identical.", details={"id": old})
    keys = set(reference_keys or ["entityId", "sourceEntityId", "targetEntityId", "refEntityId"])
    keys.add("id")
    return _run_refactor(
        solution_path=solution_path,
        apply=apply,
        transform=lambda node: _replace_int_values_for_keys(node, keys=keys, old=old, new=new),
    )


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
