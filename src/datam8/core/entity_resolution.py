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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.core.locator_codec import (
    locator_to_string,
    model_locator_to_relpath,
    parse_locator,
)
from datam8.core.paths import safe_join
from datam8.core.solution_index import (
    find_index_entry_by_locator,
    iter_index_entries,
    iter_index_paths,
    parse_index_locator,
    read_index,
    relpath_from_index_abs_path,
    relpath_from_locator,
)
from datam8.core.workspace_io import list_model_entities, read_solution
from datam8_model.model import Locator


@dataclass(frozen=True)
class ResolvedEntity:
    rel_path: str
    abs_path: str
    locator: Locator | None = None
    name: str | None = None
    id: int | None = None


def resolve_model_entity(
    selector: str,
    *,
    solution_path: str | None,
    by: str = "auto",
) -> ResolvedEntity:
    """Resolve a model entity from different selector forms.

    Parameters
    ----------
    selector : str
        Entity selector value (relPath, locator, id, or name).
    solution_path : str | None
        Optional explicit solution path.
    by : str
        Selector mode (`auto`, `relPath`, `locator`, `id`, `name`).

    Returns
    -------
    ResolvedEntity
        Resolved entity metadata with absolute and relative paths.

    Raises
    ------
    Datam8ValidationError
        If selector input is invalid or ambiguous."""
    sel = (selector or "").strip()
    if not sel:
        raise Datam8ValidationError(message="Empty entity selector.", details=None)

    if by not in {"auto", "relPath", "locator", "id", "name"}:
        raise Datam8ValidationError(message="Invalid --by.", details={"by": by})

    if by == "relPath":
        return _resolve_by_relpath(sel, solution_path)
    if by == "locator":
        return _resolve_by_locator(sel, solution_path)
    if by == "id":
        try:
            return _resolve_by_id(int(sel), solution_path)
        except ValueError:
            raise Datam8ValidationError(message="Invalid id.", details={"id": sel})
    if by == "name":
        return _resolve_by_name(sel, solution_path)

    # auto
    if sel.startswith("/"):
        return _resolve_by_locator(sel, solution_path)
    if sel.lower().endswith(".json") and ("/" in sel or "\\" in sel):
        return _resolve_by_relpath(sel, solution_path)
    if sel.isdigit():
        return _resolve_by_id(int(sel), solution_path)
    if "/" in sel or "\\" in sel:
        return _resolve_by_relpath(sel, solution_path)
    return _resolve_by_name(sel, solution_path)


def _resolve_by_relpath(rel_path: str, solution_path: str | None) -> ResolvedEntity:
    resolved, _sol = read_solution(solution_path)
    abs_path = safe_join(resolved.root_dir, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": rel_path})
    info = _try_read_entity_info(abs_path)
    return ResolvedEntity(rel_path=abs_path.relative_to(resolved.root_dir).as_posix(), abs_path=str(abs_path), **info)


def _resolve_by_locator(locator: str, solution_path: str | None) -> ResolvedEntity:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    try:
        loc = parse_locator(locator)
    except Exception as e:
        raise Datam8ValidationError(message="Invalid locator.", details={"locator": locator, "error": str(e)})
    if loc.entityType != "modelEntities":
        raise Datam8ValidationError(
            message="Model entity locator must have entityType 'modelEntities'.",
            details={"locator": loc.model_dump(mode="json")},
        )

    # 1) Prefer index.json (if present and usable)
    try:
        idx = read_index(solution_path)
        found = find_index_entry_by_locator(idx, loc)
        if found:
            rel = relpath_from_index_abs_path(found, root=root) or _require_model_relpath(loc, model_path=str(sol.modelPath))
            abs_path = safe_join(root, rel)
            if abs_path.exists():
                info = _try_read_entity_info(abs_path)
                return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=loc, **info)
    except Exception:
        pass

    # 2) Deterministic from locator
    rel = _require_model_relpath(loc, model_path=str(sol.modelPath))
    abs_path = safe_join(root, rel)
    if abs_path.exists():
        info = _try_read_entity_info(abs_path)
        return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=loc, **info)

    # 3) Scan
    entities = list_model_entities(solution_path)
    for e in entities:
        if locator_to_string(e.locator) == locator_to_string(loc):
            abs_path = safe_join(root, e.relPath)
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=e.relPath, abs_path=str(abs_path), locator=loc, name=e.name, **info)

    raise Datam8NotFoundError(message="Entity not found by locator.", details={"locator": loc.model_dump(mode="json")})


def _resolve_by_id(entity_id: int, solution_path: str | None) -> ResolvedEntity:
    if entity_id < 0:
        raise Datam8ValidationError(message="Invalid id.", details={"id": entity_id})
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir

    # Prefer index.json to limit scan set.
    candidates: list[str] = []
    try:
        idx = read_index(solution_path)
        for p in iter_index_paths(idx, root=root, model_path=str(sol.modelPath)):
            candidates.append(p)
    except Exception:
        candidates = []

    if candidates:
        for rel in candidates:
            abs_path = safe_join(root, rel)
            info = _try_read_entity_info(abs_path)
            if info.get("id") == entity_id:
                return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), **info)

    for e in list_model_entities(solution_path):
        if e.content.id == entity_id:
            abs_path = safe_join(root, e.relPath)
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=e.relPath, abs_path=str(abs_path), locator=e.locator, name=e.name, **info)

    raise Datam8NotFoundError(message="Entity not found by id.", details={"id": entity_id})


def _resolve_by_name(name: str, solution_path: str | None) -> ResolvedEntity:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    n = name.strip()

    # Prefer index.json for quick exact matches
    matches: list[dict[str, Any]] = []
    try:
        idx = read_index(solution_path)
        for entry in iter_index_entries(idx):
            if entry.get("name") == n:
                matches.append(entry)
    except Exception:
        matches = []

    if matches:
        if len(matches) > 1:
            raise Datam8ValidationError(
                message="Ambiguous entity name; use --by locator or provide a relPath.",
                details={"name": n, "matches": [{"locator": m.get("locator"), "absPath": m.get("absPath")} for m in matches]},
            )
        loc = parse_index_locator(matches[0].get("locator"))
        rel = relpath_from_index_abs_path(matches[0], root=root) or (model_locator_to_relpath(locator=loc, model_path=str(sol.modelPath)) if loc else None)
        if rel is None:
            raise Datam8NotFoundError(message="Entity not found by name.", details={"name": n})
        abs_path = safe_join(root, rel)
        if abs_path.exists():
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=loc, **info)

    entities = list_model_entities(solution_path)
    candidates = [e for e in entities if e.name == n]
    if not candidates:
        raise Datam8NotFoundError(message="Entity not found by name.", details={"name": n})
    if len(candidates) > 1:
        raise Datam8ValidationError(
            message="Ambiguous entity name; use --by locator or provide a relPath.",
            details={
                "name": n,
                "matches": [{"relPath": e.relPath, "locator": e.locator.model_dump(mode="json")} for e in candidates],
            },
        )
    e = candidates[0]
    abs_path = safe_join(root, e.relPath)
    info = _try_read_entity_info(abs_path)
    return ResolvedEntity(rel_path=e.relPath, abs_path=str(abs_path), locator=e.locator, name=e.name, **info)


def _try_read_entity_info(abs_path: Path) -> dict[str, Any]:
    try:
        raw = abs_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(data.get("id"), int):
        out["id"] = data["id"]
    if isinstance(data.get("name"), str):
        out["name"] = data["name"]
    return out


def _require_model_relpath(locator: Locator, *, model_path: str) -> str:
    rel = relpath_from_locator(locator, model_path=model_path)
    if rel is None:
        raise Datam8ValidationError(
            message="Model entity locator must have entityType 'modelEntities'.",
            details={"locator": locator.model_dump(mode="json")},
        )
    return rel

