from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field, ValidationError

from datam8.core.atomic import atomic_write_json, atomic_write_text
from datam8.core.errors import Datam8ConflictError, Datam8NotFoundError, Datam8ValidationError
from datam8.core.paths import ResolvedSolution, resolve_solution, safe_join


class GeneratorTarget(BaseModel):
    name: str
    isDefault: Optional[bool] = None
    sourcePath: str
    outputPath: str


class Solution(BaseModel):
    schemaVersion: str
    basePath: str
    modelPath: str
    generatorTargets: list[GeneratorTarget]


def read_solution(solution_path: Optional[str]) -> tuple[ResolvedSolution, Solution]:
    resolved = resolve_solution(solution_path or os.environ.get("DATAM8_SOLUTION_PATH"))
    try:
        raw = resolved.solution_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Datam8NotFoundError(message="Solution file not found.", details={"solution": str(resolved.solution_file)})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Datam8ValidationError(
            message="Invalid JSON in solution file.",
            details={"solution": str(resolved.solution_file), "error": str(e)},
        )
    try:
        sol = Solution.model_validate(data)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Solution file validation failed.",
            details={"solution": str(resolved.solution_file), "errors": e.errors()},
        )
    return resolved, sol


def _normalize_locator(rel_path: str) -> str:
    without_ext = re.sub(r"\.json$", "", rel_path, flags=re.IGNORECASE)
    return "/" + without_ext.replace("\\", "/").lstrip("/")


def _iter_json_files(root: Path, rel_dir: str, *, ignore: Iterable[str] = ()) -> list[Path]:
    base_dir = safe_join(root, rel_dir)
    if not base_dir.exists():
        return []
    ignore_set = {p.replace("\\", "/") for p in ignore}

    results: list[Path] = []
    for path in base_dir.rglob("*.json"):
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            continue
        if not resolved.is_relative_to(root.resolve()):
            continue
        rel = resolved.relative_to(root).as_posix()
        if any(rel.endswith(ig) or rel == ig for ig in ignore_set):
            continue
        results.append(resolved)
    results.sort(key=lambda p: p.as_posix().lower())
    return results


def _read_json_file(abs_path: Path) -> Any:
    try:
        raw = abs_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Datam8NotFoundError(message="File not found.", details={"path": str(abs_path)})
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise Datam8ValidationError(message="Invalid JSON.", details={"path": str(abs_path), "error": str(e)})


def read_workspace_json(rel_path: str, solution_path: Optional[str]) -> Any:
    resolved, _sol = read_solution(solution_path)
    abs_path = safe_join(resolved.root_dir, rel_path)
    return _read_json_file(abs_path)


@dataclass(frozen=True)
class ModelEntityEntry:
    locator: str
    name: str
    absPath: str
    relPath: str
    content: Any


@dataclass(frozen=True)
class BaseEntityEntry:
    name: str
    absPath: str
    relPath: str
    content: Any


def list_base_entities(solution_path: Optional[str]) -> list[BaseEntityEntry]:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    files = _iter_json_files(root, sol.basePath)
    entries: list[BaseEntityEntry] = []
    for abs_path in files:
        rel = abs_path.relative_to(root).as_posix()
        entries.append(
            BaseEntityEntry(
                name=abs_path.stem,
                absPath=str(abs_path),
                relPath=rel,
                content=_read_json_file(abs_path),
            )
        )
    return entries


def list_model_entities(solution_path: Optional[str]) -> list[ModelEntityEntry]:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    files = _iter_json_files(root, sol.modelPath, ignore=[".properties.json"])
    entities: list[ModelEntityEntry] = []
    for abs_path in files:
        rel = abs_path.relative_to(root).as_posix()
        entities.append(
            ModelEntityEntry(
                locator=_normalize_locator(rel),
                name=abs_path.stem,
                absPath=str(abs_path),
                relPath=rel,
                content=_read_json_file(abs_path),
            )
        )
    return entities


def _sanitize_path_segment(value: str) -> str:
    trimmed = str(value or "").strip()
    return trimmed.replace("\\", "_").replace("/", "_").replace("\0", "")


def _parse_entity_name_from_model_entity(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    name = content.get("name")
    return name.strip() if isinstance(name, str) else ""


def _derive_function_source_folder_name(rel_path: str, entity_name: str) -> str:
    safe = _sanitize_path_segment(entity_name)
    if safe:
        return safe
    return _sanitize_path_segment(Path(rel_path).stem)


def _read_model_entity_name(abs_path: Path) -> str:
    try:
        data = _read_json_file(abs_path)
    except Exception:
        return ""
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"].strip()
    return ""


def _merge_directories(from_abs: Path, to_abs: Path) -> None:
    to_abs.mkdir(parents=True, exist_ok=True)
    for entry in from_abs.iterdir():
        src = entry
        dst = to_abs / entry.name
        if entry.is_dir():
            _merge_directories(src, dst)
            continue
        if entry.is_file():
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
    try:
        if not any(from_abs.iterdir()):
            from_abs.rmdir()
    except Exception:
        pass


def _copy_directory(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        s = entry
        d = dst / entry.name
        if entry.is_dir():
            _copy_directory(s, d)
            continue
        if entry.is_file():
            if d.exists():
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(s.read_bytes())


def _ensure_function_source_folder_name(
    *,
    root: Path,
    rel_path: str,
    prev_entity_name: str,
    next_entity_name: str,
) -> None:
    dir_rel = Path(rel_path).parent.as_posix()
    from_name = _derive_function_source_folder_name(rel_path, prev_entity_name)
    to_name = _derive_function_source_folder_name(rel_path, next_entity_name)
    if not from_name or not to_name or from_name == to_name:
        return
    from_abs = safe_join(root, f"{dir_rel}/{from_name}" if dir_rel != "." else from_name)
    to_abs = safe_join(root, f"{dir_rel}/{to_name}" if dir_rel != "." else to_name)
    if not from_abs.exists():
        return
    if not to_abs.exists():
        to_abs.parent.mkdir(parents=True, exist_ok=True)
        from_abs.rename(to_abs)
        return
    _merge_directories(from_abs, to_abs)


def _move_function_source_folder(*, root: Path, from_rel_path: str, to_rel_path: str, entity_name: str) -> None:
    from_dir = Path(from_rel_path).parent.as_posix()
    to_dir = Path(to_rel_path).parent.as_posix()
    folder_name = _derive_function_source_folder_name(from_rel_path, entity_name)
    if not folder_name:
        return
    from_abs = safe_join(root, f"{from_dir}/{folder_name}" if from_dir != "." else folder_name)
    if not from_abs.exists():
        return
    to_abs = safe_join(root, f"{to_dir}/{folder_name}" if to_dir != "." else folder_name)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    if to_abs.exists():
        _merge_directories(from_abs, to_abs)
        return
    from_abs.rename(to_abs)


def write_model_entity(rel_path: str, content: Any, solution_path: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    prev_entity_name = _read_model_entity_name(abs_path) if abs_path.exists() else ""
    next_entity_name = _parse_entity_name_from_model_entity(content)
    _ensure_function_source_folder_name(
        root=root,
        rel_path=rel_path,
        prev_entity_name=prev_entity_name,
        next_entity_name=next_entity_name,
    )
    atomic_write_json(abs_path, content, indent=4)
    _migrate_legacy_function_sources(root=root, rel_path=rel_path, content=content)
    return str(abs_path)


def create_model_entity(rel_path: str, *, name: Optional[str], solution_path: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if abs_path.exists():
        raise Datam8ConflictError(message="Model entity already exists.", details={"relPath": rel_path})
    entity_name = (name or "").strip() or Path(rel_path).stem
    content: dict[str, Any] = {"name": entity_name}
    atomic_write_json(abs_path, content, indent=4)
    return str(abs_path)


def delete_model_entity(rel_path: str, solution_path: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": rel_path})
    abs_path.unlink()
    return str(abs_path)


def delete_base_entity(rel_path: str, solution_path: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Base entity not found.", details={"relPath": rel_path})
    abs_path.unlink()
    return str(abs_path)


def move_model_entity(from_rel_path: str, to_rel_path: str, solution_path: Optional[str]) -> dict[str, str]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_rel_path)
    to_abs = safe_join(root, to_rel_path)
    if not from_abs.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": from_rel_path})
    entity_name = _read_model_entity_name(from_abs)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    _move_function_source_folder(root=root, from_rel_path=from_rel_path, to_rel_path=to_rel_path, entity_name=entity_name)
    return {"from": str(from_abs), "to": str(to_abs)}


def duplicate_model_entity(
    from_rel_path: str,
    to_rel_path: str,
    *,
    solution_path: Optional[str],
    new_name: Optional[str] = None,
    new_id: Optional[int] = None,
) -> dict[str, str]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_rel_path)
    to_abs = safe_join(root, to_rel_path)
    if not from_abs.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": from_rel_path})
    if to_abs.exists():
        raise Datam8ConflictError(message="Target model entity already exists.", details={"relPath": to_rel_path})
    content = _read_json_file(from_abs)
    if isinstance(content, dict):
        if new_name is not None:
            content["name"] = new_name
        if new_id is not None:
            content["id"] = new_id
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(to_abs, content, indent=4)

    entity_name = _read_model_entity_name(from_abs)
    from_folder = _derive_function_source_folder_name(from_rel_path, entity_name)
    to_folder = _derive_function_source_folder_name(to_rel_path, _parse_entity_name_from_model_entity(content))
    if from_folder and to_folder:
        from_dir_rel = Path(from_rel_path).parent.as_posix()
        to_dir_rel = Path(to_rel_path).parent.as_posix()
        from_folder_abs = safe_join(root, f"{from_dir_rel}/{from_folder}" if from_dir_rel != "." else from_folder)
        to_folder_abs = safe_join(root, f"{to_dir_rel}/{to_folder}" if to_dir_rel != "." else to_folder)
        if from_folder_abs.exists() and from_folder_abs.is_dir():
            _copy_directory(from_folder_abs, to_folder_abs)

    return {"from": str(from_abs), "to": str(to_abs)}


def write_base_entity(rel_path: str, content: Any, solution_path: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    atomic_write_json(abs_path, content, indent=4)
    return str(abs_path)


def regenerate_index(solution_path: Optional[str]) -> dict[str, Any]:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    entities = list_model_entities(solution_path)

    def zone_to_key(segment: str) -> str:
        m = re.match(r"^\d+\-([A-Za-z]+)", segment)
        slug = m.group(1).lower() if m else segment.lower()
        return f"{slug}Index"

    index: dict[str, dict[str, list[dict[str, str]]]] = {}
    for entity in entities:
        try:
            rel_from_model = Path(entity.relPath).relative_to(Path(sol.modelPath)).as_posix()
        except Exception:
            rel_from_model = Path(entity.relPath).as_posix()
        zone_segment = rel_from_model.split("/")[0] if rel_from_model else "model"
        key = zone_to_key(zone_segment or "model")
        index.setdefault(key, {"entry": []})
        index[key]["entry"].append({"locator": entity.locator, "name": entity.name, "absPath": entity.absPath})

    for k in sorted(index.keys()):
        index[k]["entry"].sort(key=lambda e: (e["locator"], e["name"]))

    index_path = root / "index.json"
    atomic_write_json(index_path, index, indent=4)
    return index


def list_directory(dir_path: Optional[str]) -> list[dict[str, str]]:
    target = Path(dir_path).expanduser() if dir_path else Path.cwd()
    if not target.exists():
        raise Datam8NotFoundError(message="Directory not found.", details={"path": str(target)})
    if not target.is_dir():
        raise Datam8ValidationError(message="Path is not a directory.", details={"path": str(target)})
    entries = []
    for e in os.scandir(target):
        if e.is_dir():
            entries.append({"name": e.name, "path": str(Path(target, e.name)), "type": "dir"})
        elif e.is_file() and e.name.lower().endswith(".dm8s"):
            entries.append({"name": e.name, "path": str(Path(target, e.name)), "type": "file"})
    entries.sort(key=lambda x: x["name"].lower())
    return entries


def _ensure_basename(value: str) -> None:
    if not value or Path(value).name != value or ".." in value:
        raise Datam8ValidationError(message="Invalid function source filename.", details={"value": value})


def _resolve_safe_function_source_path(entity_dir: Path, source_file: str) -> Path:
    if not source_file or not isinstance(source_file, str):
        raise Datam8ValidationError(message="Invalid function source path.", details={"source": source_file})
    if "\0" in source_file:
        raise Datam8ValidationError(message="Invalid function source path.", details={"source": source_file})
    if "\\" in source_file:
        raise Datam8ValidationError(
            message="Function source path must use forward slashes ('/').", details={"source": source_file}
        )
    if source_file.startswith("/") or re.match(r"^[A-Za-z]:", source_file):
        raise Datam8ValidationError(message="Function source path must be relative.", details={"source": source_file})

    parts = [p for p in source_file.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise Datam8ValidationError(
            message="Function source path must not contain '.' or '..'.", details={"source": source_file}
        )

    abs_path = (entity_dir / Path(*parts)).resolve()
    if not abs_path.is_relative_to(entity_dir.resolve()):
        raise Datam8ValidationError(message="Function source path escapes the entity directory.", details={"source": source_file})
    return abs_path


def _resolve_function_source_folder_name(
    *,
    root: Path,
    rel_path: str,
    preferred_entity_name: Optional[str] = None,
) -> tuple[str, str]:
    entity_abs = safe_join(root, rel_path)
    entity_name = (preferred_entity_name or "").strip() or (_read_model_entity_name(entity_abs) if entity_abs.exists() else "")
    folder_name = _derive_function_source_folder_name(rel_path, entity_name)
    fallback_folder_name = _sanitize_path_segment(Path(rel_path).stem)
    return folder_name, fallback_folder_name


def _resolve_function_source_abs_path(
    *,
    root: Path,
    rel_path: str,
    source_file: str,
    preferred_folder_name: Optional[str] = None,
) -> Path:
    _ensure_basename(source_file)
    dir_rel = Path(rel_path).parent.as_posix()
    if preferred_folder_name:
        folder_name = preferred_folder_name
        fallback_folder_name = _sanitize_path_segment(Path(rel_path).stem)
    else:
        folder_name, fallback_folder_name = _resolve_function_source_folder_name(root=root, rel_path=rel_path)

    primary = safe_join(root, f"{dir_rel}/{folder_name}/{source_file}" if dir_rel != "." else f"{folder_name}/{source_file}")
    if primary.exists():
        return primary
    fallback = safe_join(
        root,
        f"{dir_rel}/{fallback_folder_name}/{source_file}" if dir_rel != "." else f"{fallback_folder_name}/{source_file}",
    )
    if fallback != primary and fallback.exists():
        return fallback
    legacy_adjacent = safe_join(root, f"{dir_rel}/{source_file}" if dir_rel != "." else source_file)
    if legacy_adjacent.exists():
        return legacy_adjacent
    return primary


def _migrate_legacy_function_source_file(*, root: Path, rel_path: str, source_file: str, folder_name: str) -> None:
    dir_rel = Path(rel_path).parent.as_posix()
    legacy_abs = safe_join(root, f"{dir_rel}/{source_file}" if dir_rel != "." else source_file)
    primary_abs = safe_join(
        root,
        f"{dir_rel}/{folder_name}/{source_file}" if dir_rel != "." else f"{folder_name}/{source_file}",
    )
    if legacy_abs == primary_abs or not legacy_abs.exists():
        return
    if primary_abs.exists():
        try:
            legacy_abs.unlink()
        except Exception:
            pass
        return
    primary_abs.parent.mkdir(parents=True, exist_ok=True)
    legacy_abs.rename(primary_abs)


def _migrate_legacy_function_sources(*, root: Path, rel_path: str, content: Any) -> None:
    entity_name = _parse_entity_name_from_model_entity(content)
    folder_name, _fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    transforms = content.get("transformations") if isinstance(content, dict) else None
    if not isinstance(transforms, list):
        return
    sources: list[str] = []
    for t in transforms:
        if not isinstance(t, dict) or t.get("kind") != "function":
            continue
        fn = t.get("function")
        if not isinstance(fn, dict):
            continue
        src = fn.get("source")
        if isinstance(src, str) and src.strip():
            sources.append(src.strip())
    for src in sources:
        try:
            _ensure_basename(src)
            _migrate_legacy_function_source_file(root=root, rel_path=rel_path, source_file=src, folder_name=folder_name)
        except Exception:
            continue


def read_function_source(rel_path: str, source_file: str, solution_path: Optional[str], entity_name: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = _resolve_safe_function_source_path(entity_dir, source_file)
        return abs_path.read_text(encoding="utf-8")

    folder_name, _fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    abs_path = _resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=source_file, preferred_folder_name=folder_name)
    return abs_path.read_text(encoding="utf-8")


def write_function_source(
    rel_path: str,
    source_file: str,
    content: str,
    solution_path: Optional[str],
    entity_name: Optional[str],
) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = _resolve_safe_function_source_path(entity_dir, source_file)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(abs_path, content)
        return str(abs_path)

    _ensure_basename(source_file)
    folder_name, _fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    abs_path = safe_join(
        root,
        f"{dir_rel}/{folder_name}/{source_file}" if dir_rel != "." else f"{folder_name}/{source_file}",
    )
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(abs_path, content)
    _migrate_legacy_function_source_file(root=root, rel_path=rel_path, source_file=source_file, folder_name=folder_name)
    return str(abs_path)


def rename_function_source(
    rel_path: str,
    from_source: str,
    to_source: str,
    solution_path: Optional[str],
    entity_name: Optional[str],
) -> dict[str, Any]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)
    folder_name, _fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)

    if isinstance(from_source, str) and "/" in from_source:
        from_abs = _resolve_safe_function_source_path(entity_dir, from_source)
    else:
        from_abs = _resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=from_source, preferred_folder_name=folder_name)

    if not (isinstance(to_source, str) and "/" in to_source):
        _ensure_basename(to_source)
        to_abs = safe_join(
            root,
            f"{dir_rel}/{folder_name}/{to_source}" if dir_rel != "." else f"{folder_name}/{to_source}",
        )
    else:
        to_abs = _resolve_safe_function_source_path(entity_dir, to_source)

    if not from_abs.exists():
        return {"fromAbsPath": str(from_abs), "toAbsPath": str(to_abs), "skipped": True}
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    if not (isinstance(to_source, str) and "/" in to_source):
        _migrate_legacy_function_source_file(root=root, rel_path=rel_path, source_file=to_source, folder_name=folder_name)
    return {"fromAbsPath": str(from_abs), "toAbsPath": str(to_abs)}


def delete_function_source(rel_path: str, source_file: str, solution_path: Optional[str], entity_name: Optional[str]) -> str:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = _resolve_safe_function_source_path(entity_dir, source_file)
    else:
        folder_name, _fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
        abs_path = _resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=source_file, preferred_folder_name=folder_name)

    if not abs_path.exists():
        raise Datam8NotFoundError(message="Script not found.", details={"source": source_file})
    abs_path.unlink()
    return str(abs_path)


def list_function_sources(
    rel_path: str, solution_path: Optional[str], entity_name: Optional[str], *, include_unreferenced: bool = True
) -> list[str]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    entity_abs = safe_join(root, rel_path)
    if not entity_abs.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": rel_path})
    content = _read_json_file(entity_abs)

    referenced: set[str] = set()
    if isinstance(content, dict):
        transforms = content.get("transformations")
        if isinstance(transforms, list):
            for t in transforms:
                if not isinstance(t, dict) or t.get("kind") != "function":
                    continue
                fn = t.get("function")
                if isinstance(fn, dict) and isinstance(fn.get("source"), str) and fn["source"].strip():
                    referenced.add(fn["source"].strip())

    if not include_unreferenced:
        return sorted(referenced)

    folder_name, fallback = _resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    dir_rel = Path(rel_path).parent.as_posix()
    base_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    scan_dirs: list[Path] = []
    for seg in [folder_name, fallback]:
        if not seg:
            continue
        p = safe_join(root, f"{dir_rel}/{seg}" if dir_rel != "." else seg)
        if p.exists() and p.is_dir():
            scan_dirs.append(p)
    scan_dirs.append(base_dir)

    files: set[str] = set(referenced)
    for d in scan_dirs:
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() == ".json":
                continue
            if d == base_dir:
                files.add(f.relative_to(base_dir).as_posix())
            else:
                files.add(f.name)
    return sorted(files)


def create_new_project(
    *,
    solution_name: str,
    project_root: str,
    base_path: Optional[str],
    model_path: Optional[str],
    target: str,
) -> str:
    if not solution_name or not project_root or not target:
        raise Datam8ValidationError(message="solutionName, projectRoot and target are required", details=None)

    base_path_segment = base_path or "Base"
    model_path_segment = model_path or "Model"

    project_dir = Path(project_root) / solution_name
    base_dir = project_dir / base_path_segment
    model_dir = project_dir / model_path_segment
    generator_dir = project_dir / "Generate" / target
    output_dir = project_dir / "Output" / target / "generated"
    solution_file_path = project_dir / f"{solution_name}.dm8s"

    if project_dir.exists():
        raise Datam8ConflictError(message=f"Project directory already exists at {project_dir}", details={"projectDir": str(project_dir)})
    if solution_file_path.exists():
        raise Datam8ConflictError(message=f"Solution already exists at {solution_file_path}", details={"solutionPath": str(solution_file_path)})

    for d in (project_dir, base_dir, model_dir, generator_dir, output_dir):
        d.mkdir(parents=True, exist_ok=True)

    solution_content = {
        "schemaVersion": "2.0.0",
        "basePath": base_path_segment,
        "modelPath": model_path_segment,
        "generatorTargets": [
            {
                "name": target,
                "isDefault": True,
                "sourcePath": f"Generate/{target}",
                "outputPath": f"Output/{target}/generated",
            }
        ],
    }

    default_attribute_types = [
        {"name": "ID", "displayName": "ID", "defaultType": "int", "canBeInRelation": True, "isDefaultProperty": False},
        {
            "name": "Name",
            "displayName": "Name",
            "defaultType": "string",
            "defaultLength": 256,
            "canBeInRelation": False,
            "isDefaultProperty": True,
        },
        {
            "name": "Description",
            "displayName": "Description",
            "defaultType": "string",
            "defaultLength": 512,
            "canBeInRelation": False,
            "isDefaultProperty": False,
        },
        {"name": "Date", "displayName": "Date", "defaultType": "datetime", "canBeInRelation": False, "isDefaultProperty": False},
        {"name": "Flag", "displayName": "Flag", "defaultType": "boolean", "canBeInRelation": False, "isDefaultProperty": False},
    ]

    default_data_types = [
        {"name": "string", "displayName": "Unicode String", "hasCharLen": True, "hasPrecision": False, "hasScale": False},
        {"name": "int", "displayName": "Integer (32 bit)", "hasCharLen": False, "hasPrecision": False, "hasScale": False},
        {"name": "long", "displayName": "Integer (64 bit)", "hasCharLen": False, "hasPrecision": False, "hasScale": False},
        {"name": "double", "displayName": "Double", "hasCharLen": False, "hasPrecision": False, "hasScale": False},
        {"name": "decimal", "displayName": "Decimal", "hasCharLen": False, "hasPrecision": True, "hasScale": True},
        {"name": "datetime", "displayName": "DateTime", "hasCharLen": False, "hasPrecision": False, "hasScale": False},
        {"name": "boolean", "displayName": "Boolean", "hasCharLen": False, "hasPrecision": False, "hasScale": False},
    ]

    base_files: dict[str, Any] = {
        "AttributeTypes": {"type": "attributeTypes", "attributeTypes": default_attribute_types},
        "DataTypes": {"type": "dataTypes", "dataTypes": default_data_types},
        "DataSourceTypes": {"type": "dataSourceTypes", "dataSourceTypes": []},
        "DataSources": {"type": "dataSources", "dataSources": []},
        "DataProducts": {"type": "dataProducts", "dataProducts": []},
        "Zones": {"type": "zones", "zones": []},
        "Properties": {"type": "properties", "properties": []},
        "PropertyValues": {"type": "propertyValues", "propertyValues": []},
    }

    atomic_write_json(solution_file_path, solution_content, indent=4)
    for name, content in base_files.items():
        atomic_write_json(base_dir / f"{name}.json", content, indent=4)

    return str(solution_file_path)


def rename_folder(from_folder_rel_path: str, to_folder_rel_path: str, solution_path: Optional[str]) -> dict[str, str]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_folder_rel_path)
    to_abs = safe_join(root, to_folder_rel_path)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    return {"from": str(from_abs), "to": str(to_abs)}


def refactor_properties(
    *,
    solution_path: Optional[str],
    property_renames: list[dict[str, str]],
    value_renames: list[dict[str, str]],
    deleted_properties: list[str],
    deleted_values: list[dict[str, str]],
) -> dict[str, int]:
    prop_map: dict[str, str] = {r["oldName"]: r["newName"] for r in (property_renames or []) if r.get("oldName") and r.get("newName")}
    value_map: dict[str, dict[str, str]] = {}
    for v in value_renames or []:
        prop = v.get("property")
        if not prop:
            continue
        value_map.setdefault(prop, {})[v.get("oldValue", "")] = v.get("newValue", "")
    deleted_prop_set = set(deleted_properties or [])
    deleted_value_set = {f'{d.get("property","")}::{d.get("value","")}' for d in (deleted_values or [])}

    def transform_node(node: Any, *, in_properties_array: bool = False) -> tuple[bool, Any]:
        if node is None:
            return False, node
        if isinstance(node, list):
            next_list: list[Any] = []
            changed = False
            for item in node:
                if in_properties_array and isinstance(item, dict):
                    prop_name = item.get("property")
                    val_name = item.get("value")
                    if isinstance(prop_name, str) and isinstance(val_name, str):
                        if prop_name in deleted_prop_set:
                            changed = True
                            continue
                        if f"{prop_name}::{val_name}" in deleted_value_set:
                            changed = True
                            continue
                        next_prop = prop_map.get(prop_name, prop_name)
                        next_val = value_map.get(prop_name, {}).get(val_name, val_name)
                        updated = {**item, "property": next_prop, "value": next_val}
                        if next_prop != prop_name or next_val != val_name:
                            changed = True
                        next_list.append(updated)
                        continue
                c, v = transform_node(item, in_properties_array=False)
                if c:
                    changed = True
                next_list.append(v)
            return changed, next_list
        if isinstance(node, dict):
            changed = False
            clone: dict[str, Any] = dict(node)
            for key in list(clone.keys()):
                child = clone[key]
                in_props = key == "properties"
                c, v = transform_node(child, in_properties_array=in_props)
                if c:
                    changed = True
                clone[key] = v
            return changed, clone
        return False, node

    base_entries = list_base_entities(solution_path)
    model_entries = list_model_entities(solution_path)
    updated = 0

    for entry in [*base_entries, *model_entries]:
        changed, value = transform_node(entry.content)
        if changed:
            atomic_write_json(Path(entry.absPath), value, indent=4)
            updated += 1

    return {"updatedFiles": updated}
