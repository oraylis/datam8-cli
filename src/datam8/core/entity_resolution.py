from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.core.indexing import read_index
from datam8.core.paths import safe_join
from datam8.core.workspace_io import list_model_entities, read_solution


@dataclass(frozen=True)
class ResolvedEntity:
    rel_path: str
    abs_path: str
    locator: Optional[str] = None
    name: Optional[str] = None
    id: Optional[int] = None


def resolve_model_entity(
    selector: str,
    *,
    solution_path: Optional[str],
    by: str = "auto",
) -> ResolvedEntity:
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


def _resolve_by_relpath(rel_path: str, solution_path: Optional[str]) -> ResolvedEntity:
    resolved, _sol = read_solution(solution_path)
    abs_path = safe_join(resolved.root_dir, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": rel_path})
    info = _try_read_entity_info(abs_path)
    return ResolvedEntity(rel_path=abs_path.relative_to(resolved.root_dir).as_posix(), abs_path=str(abs_path), **info)


def _resolve_by_locator(locator: str, solution_path: Optional[str]) -> ResolvedEntity:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    loc = locator.strip()
    if not loc.startswith("/"):
        raise Datam8ValidationError(message="Locator must start with '/'.", details={"locator": locator})

    # 1) Prefer index.json (if present and usable)
    try:
        idx = read_index(solution_path)
        found = _find_index_entry_by_locator(idx, loc)
        if found:
            rel = _rel_from_index_entry(found, root) or _rel_from_locator(loc)
            abs_path = safe_join(root, rel)
            if abs_path.exists():
                info = _try_read_entity_info(abs_path)
                return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=loc, **info)
    except Exception:
        pass

    # 2) Deterministic from locator
    rel = _rel_from_locator(loc)
    abs_path = safe_join(root, rel)
    if abs_path.exists():
        info = _try_read_entity_info(abs_path)
        return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=loc, **info)

    # 3) Scan
    entities = list_model_entities(solution_path)
    for e in entities:
        if e.locator == loc:
            abs_path = safe_join(root, e.relPath)
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=e.relPath, abs_path=str(abs_path), locator=loc, name=e.name, **info)

    raise Datam8NotFoundError(message="Entity not found by locator.", details={"locator": locator})


def _resolve_by_id(entity_id: int, solution_path: Optional[str]) -> ResolvedEntity:
    if entity_id < 0:
        raise Datam8ValidationError(message="Invalid id.", details={"id": entity_id})
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir

    # Prefer index.json to limit scan set.
    candidates: list[str] = []
    try:
        idx = read_index(solution_path)
        for p in _iter_index_paths(idx, root):
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
        if isinstance(e.content, dict) and e.content.get("id") == entity_id:
            abs_path = safe_join(root, e.relPath)
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=e.relPath, abs_path=str(abs_path), locator=e.locator, name=e.name, **info)

    raise Datam8NotFoundError(message="Entity not found by id.", details={"id": entity_id})


def _resolve_by_name(name: str, solution_path: Optional[str]) -> ResolvedEntity:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    n = name.strip()

    # Prefer index.json for quick exact matches
    matches: list[dict[str, Any]] = []
    try:
        idx = read_index(solution_path)
        for entry in _iter_index_entries(idx):
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
        rel = _rel_from_index_entry(matches[0], root) or _rel_from_locator(matches[0].get("locator", ""))
        abs_path = safe_join(root, rel)
        if abs_path.exists():
            info = _try_read_entity_info(abs_path)
            return ResolvedEntity(rel_path=rel, abs_path=str(abs_path), locator=matches[0].get("locator"), **info)

    entities = list_model_entities(solution_path)
    candidates = [e for e in entities if e.name == n]
    if not candidates:
        raise Datam8NotFoundError(message="Entity not found by name.", details={"name": n})
    if len(candidates) > 1:
        raise Datam8ValidationError(
            message="Ambiguous entity name; use --by locator or provide a relPath.",
            details={"name": n, "matches": [{"relPath": e.relPath, "locator": e.locator} for e in candidates]},
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


def _iter_index_entries(index: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for _k, block in index.items():
        if not isinstance(block, dict):
            continue
        ent = block.get("entry")
        if isinstance(ent, list):
            for e in ent:
                if isinstance(e, dict):
                    entries.append(e)
    return entries


def _find_index_entry_by_locator(index: dict[str, Any], locator: str) -> Optional[dict[str, Any]]:
    for e in _iter_index_entries(index):
        if e.get("locator") == locator:
            return e
    return None


def _rel_from_index_entry(entry: dict[str, Any], root: Path) -> Optional[str]:
    abs_path = entry.get("absPath")
    if isinstance(abs_path, str) and abs_path:
        try:
            p = Path(abs_path)
            if p.is_absolute():
                rp = p.resolve()
                if rp.is_relative_to(root.resolve()):
                    return rp.relative_to(root.resolve()).as_posix()
        except Exception:
            pass
    return None


def _rel_from_locator(locator: str) -> str:
    loc = locator.strip().lstrip("/")
    if loc.lower().endswith(".json"):
        return loc
    return loc + ".json"


def _iter_index_paths(index: dict[str, Any], root: Path) -> list[str]:
    rels: list[str] = []
    for e in _iter_index_entries(index):
        loc = e.get("locator")
        if isinstance(loc, str) and loc.startswith("/"):
            rels.append(_rel_from_locator(loc))
        else:
            rel = _rel_from_index_entry(e, root)
            if rel:
                rels.append(rel)
    return rels

