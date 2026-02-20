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
import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from datam8.core import legacy_function_sources
from datam8.core.atomic import atomic_write_json, atomic_write_text
from datam8.core.errors import (
    Datam8ConflictError,
    Datam8NotFoundError,
    Datam8ValidationError,
)
from datam8.core.locator_codec import (
    folder_path_to_locator,
    locator_sort_key,
    relpath_to_model_locator,
)
from datam8.core.paths import ResolvedSolution, resolve_solution, safe_join
from datam8_model import attribute as attribute_model
from datam8_model import base as base_model
from datam8_model import data_type as data_type_model
from datam8_model import folder as folder_model
from datam8_model import model as model_model
from datam8_model.solution import Solution


def read_solution(solution_path: str | None) -> tuple[ResolvedSolution, Solution]:
    """Load and validate a v2 solution file.

    Parameters
    ----------
    solution_path : str | None
        Optional path to a `.dm8s` file or containing folder. If omitted,
        `DATAM8_SOLUTION_PATH` is used.

    Returns
    -------
    tuple[ResolvedSolution, Solution]
        Tuple of resolved filesystem paths and the validated solution model.

    Raises
    ------
    Datam8NotFoundError
        If the resolved solution file does not exist.
    Datam8ValidationError
        If the solution JSON is invalid or does not match the schema."""
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


def read_workspace_json(rel_path: str, solution_path: str | None) -> Any:
    """Read a JSON file from the active workspace.

    Parameters
    ----------
    rel_path : str
        Path relative to the solution root.
    solution_path : str | None
        Optional explicit solution path.

    Returns
    -------
    Any
        Parsed JSON content."""
    resolved, _sol = read_solution(solution_path)
    abs_path = safe_join(resolved.root_dir, rel_path)
    return _read_json_file(abs_path)


def read_base_entity(rel_path: str, solution_path: str | None) -> base_model.BaseEntities:
    raw = read_workspace_json(rel_path, solution_path)
    return _validate_base_entities(raw, path=rel_path)


def read_folder_metadata(rel_path: str, solution_path: str | None) -> folder_model.Folder:
    raw = read_workspace_json(rel_path, solution_path)
    return _extract_single_folder(_validate_folder_metadata_container(raw, path=rel_path), path=rel_path)


class ModelEntityEntry(BaseModel):
    """Typed model entity payload for workspace listings."""

    locator: model_model.Locator
    name: str
    absPath: str
    relPath: str
    content: model_model.ModelEntity


class BaseEntityEntry(BaseModel):
    """Typed base entity payload for workspace listings."""

    name: str
    absPath: str
    relPath: str
    content: base_model.BaseEntities


class FolderEntityEntry(BaseModel):
    """Typed folder metadata payload for workspace listings."""

    locator: model_model.Locator
    name: str
    absPath: str
    relPath: str
    folderPath: str
    content: folder_model.Folder


def _validate_model_entity(payload: Any, *, path: str) -> model_model.ModelEntity:
    try:
        return model_model.ModelEntity.model_validate(payload)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Model entity validation failed.",
            details={"path": path, "errors": e.errors()},
        )


def _validate_base_entities(payload: Any, *, path: str) -> base_model.BaseEntities:
    try:
        return base_model.BaseEntities.model_validate(payload)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Base entity validation failed.",
            details={"path": path, "errors": e.errors()},
        )


def _coerce_folder_metadata(payload: Any, *, path: str) -> folder_model.Folder:
    try:
        return folder_model.Folder.model_validate(payload)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Folder metadata validation failed.",
            details={"path": path, "errors": e.errors()},
        )


def _validate_folder_metadata_container(payload: Any, *, path: str) -> base_model.Folders:
    try:
        return base_model.Folders.model_validate(payload)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Folder metadata validation failed.",
            details={"path": path, "errors": e.errors()},
        )


def _extract_single_folder(container: base_model.Folders, *, path: str) -> folder_model.Folder:
    folders = list(container.folders or [])
    if len(folders) != 1:
        raise Datam8ValidationError(
            message="Folder metadata validation failed.",
            details={
                "path": path,
                "errors": [
                    {
                        "type": "value_error",
                        "loc": ["folders"],
                        "msg": "Folder metadata must contain exactly one folder entry.",
                        "input": container.model_dump(mode="json"),
                    }
                ],
            },
        )
    return folders[0]


def _coerce_folder_metadata_for_write(payload: Any, *, path: str) -> base_model.Folders:
    if isinstance(payload, dict) and payload.get("type") == "folders":
        validated = _validate_folder_metadata_container(payload, path=path)
        _extract_single_folder(validated, path=path)
        return validated

    folder = _coerce_folder_metadata(payload, path=path)
    return base_model.Folders(type="folders", folders=[folder])


def _dump_sparse_json(model: BaseModel) -> Any:
    """Serialize pydantic models without materializing schema defaults."""
    return model.model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=True,
    )


class PathMutationResult(BaseModel):
    """Typed path mutation result for move/rename/duplicate operations."""

    fromAbsPath: str
    toAbsPath: str


class FunctionSourceRenameResult(BaseModel):
    """Typed result for function source rename operations."""

    fromAbsPath: str
    toAbsPath: str
    skipped: bool | None = None


class DirectoryEntry(BaseModel):
    """Typed directory listing entry."""

    name: str
    path: str
    type: str


class RefactorPropertiesResult(BaseModel):
    """Typed result for property/value refactor operations."""

    updatedFiles: int


def list_base_entities(solution_path: str | None) -> list[BaseEntityEntry]:
    """List all JSON entities below the configured base path.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.

    Returns
    -------
    list[BaseEntityEntry]
        Typed base-entity entries including metadata and parsed content."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    files = _iter_json_files(root, str(sol.basePath))
    entries: list[BaseEntityEntry] = []
    for abs_path in files:
        rel = abs_path.relative_to(root).as_posix()
        entries.append(
            BaseEntityEntry(
                name=abs_path.stem,
                absPath=str(abs_path),
                relPath=rel,
                content=_validate_base_entities(_read_json_file(abs_path), path=str(abs_path)),
            )
        )
    return entries


def list_model_entities(solution_path: str | None) -> list[ModelEntityEntry]:
    """List all model entities in the configured model path.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.

    Returns
    -------
    list[ModelEntityEntry]
        Typed model-entity entries, including locator and parsed content."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    files = _iter_json_files(root, str(sol.modelPath), ignore=[".properties.json"])
    entities: list[ModelEntityEntry] = []
    for abs_path in files:
        rel = abs_path.relative_to(root).as_posix()
        entities.append(
            ModelEntityEntry(
                locator=relpath_to_model_locator(rel_path=rel, model_path=str(sol.modelPath)),
                name=abs_path.stem,
                absPath=str(abs_path),
                relPath=rel,
                content=_validate_model_entity(_read_json_file(abs_path), path=str(abs_path)),
            )
        )
    return entities


def list_folder_entities(solution_path: str | None) -> list[FolderEntityEntry]:
    """List all folder metadata files below the configured model path."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    files = [p for p in _iter_json_files(root, str(sol.modelPath)) if p.name == ".properties.json"]
    entities: list[FolderEntityEntry] = []
    for abs_path in files:
        rel = abs_path.relative_to(root).as_posix()
        folder_rel = abs_path.parent.relative_to(safe_join(root, str(sol.modelPath))).as_posix()
        folder_path = "" if folder_rel == "." else folder_rel
        locator = folder_path_to_locator(folder_path)
        container = _validate_folder_metadata_container(_read_json_file(abs_path), path=str(abs_path))
        content = _extract_single_folder(container, path=str(abs_path))
        folder_name = content.name or abs_path.parent.name
        entities.append(
            FolderEntityEntry(
                locator=locator,
                name=folder_name,
                absPath=str(abs_path),
                relPath=rel,
                folderPath=folder_path,
                content=content,
            )
        )
    return entities


def write_model_entity(rel_path: str, content: Any, solution_path: str | None) -> str:
    """Write a model entity JSON file and run legacy source migration hooks.

    Parameters
    ----------
    rel_path : str
        Entity path relative to solution root.
    content : Any
        JSON-serializable entity payload.
    solution_path : str | None
        Optional explicit solution path.

    Returns
    -------
    str
        Absolute path of the written entity file."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    is_folder_metadata = rel_path.replace("\\", "/").endswith(".properties.json")
    validated: model_model.ModelEntity | None = None
    if not is_folder_metadata:
        validated = _validate_model_entity(content, path=rel_path)
        serialized = _dump_sparse_json(validated)
        prev_entity_name = legacy_function_sources.read_model_entity_name(abs_path) if abs_path.exists() else ""
        next_entity_name = validated.name
        legacy_function_sources.ensure_function_source_folder_name(
            root=root,
            rel_path=rel_path,
            prev_entity_name=prev_entity_name,
            next_entity_name=next_entity_name,
        )
    else:
        validated_folders = _coerce_folder_metadata_for_write(content, path=rel_path)
        serialized = _dump_sparse_json(validated_folders)
    atomic_write_json(abs_path, serialized, indent=4)
    if validated is not None:
        legacy_function_sources.migrate_legacy_function_sources(root=root, rel_path=rel_path, content=validated)
    return str(abs_path)


def create_model_entity(rel_path: str, *, name: str | None, solution_path: str | None) -> str:
    """Create model entity.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    name : str | None
        name parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    str
        Computed return value.

    Raises
    ------
    Datam8ConflictError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if abs_path.exists():
        raise Datam8ConflictError(message="Model entity already exists.", details={"relPath": rel_path})
    entity_name = (name or "").strip() or Path(rel_path).stem
    next_id = 1
    for p in _iter_json_files(root, str(_sol.modelPath), ignore=[".properties.json"]):
        data = _read_json_file(p)
        if isinstance(data, dict) and isinstance(data.get("id"), int):
            next_id = max(next_id, data["id"] + 1)

    template = model_model.ModelEntity(
        id=next_id,
        name=entity_name,
        attributes=[
            attribute_model.Attribute(
                ordinalNumber=10,
                name="id",
                attributeType="Physical",
                dataType=data_type_model.DataType(type="int", nullable=False),
                dateAdded=datetime.now(UTC),
            )
        ],
        sources=[],
        transformations=[],
        relationships=[],
    )
    atomic_write_json(abs_path, _dump_sparse_json(template), indent=4)
    return str(abs_path)


def delete_model_entity(rel_path: str, solution_path: str | None) -> str:
    """Delete model entity.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    str
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": rel_path})
    abs_path.unlink()
    return str(abs_path)


def delete_base_entity(rel_path: str, solution_path: str | None) -> str:
    """Delete base entity.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    str
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    if not abs_path.exists():
        raise Datam8NotFoundError(message="Base entity not found.", details={"relPath": rel_path})
    abs_path.unlink()
    return str(abs_path)


def move_model_entity(from_rel_path: str, to_rel_path: str, solution_path: str | None) -> PathMutationResult:
    """Move model entity.

    Parameters
    ----------
    from_rel_path : str
        from_rel_path parameter value.
    to_rel_path : str
        to_rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    PathMutationResult
        Absolute source and destination paths after move.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_rel_path)
    to_abs = safe_join(root, to_rel_path)
    if not from_abs.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": from_rel_path})
    entity_name = legacy_function_sources.read_model_entity_name(from_abs)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    legacy_function_sources.move_function_source_folder(root=root, from_rel_path=from_rel_path, to_rel_path=to_rel_path, entity_name=entity_name)
    return PathMutationResult(fromAbsPath=str(from_abs), toAbsPath=str(to_abs))


def duplicate_model_entity(
    from_rel_path: str,
    to_rel_path: str,
    *,
    solution_path: str | None,
    new_name: str | None = None,
    new_id: int | None = None,
) -> PathMutationResult:
    """Duplicate model entity.

    Parameters
    ----------
    from_rel_path : str
        from_rel_path parameter value.
    to_rel_path : str
        to_rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.
    new_name : str | None
        new_name parameter value.
    new_id : int | None
        new_id parameter value.

    Returns
    -------
    PathMutationResult
        Absolute source and destination paths for the duplicate operation.

    Raises
    ------
    Datam8ConflictError
        Raised when validation or runtime execution fails.
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_rel_path)
    to_abs = safe_join(root, to_rel_path)
    if not from_abs.exists():
        raise Datam8NotFoundError(message="Model entity not found.", details={"relPath": from_rel_path})
    if to_abs.exists():
        raise Datam8ConflictError(message="Target model entity already exists.", details={"relPath": to_rel_path})
    content = _validate_model_entity(_read_json_file(from_abs), path=str(from_abs))
    if new_name is not None:
        content.name = new_name
    if new_id is not None:
        content.id = new_id
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(to_abs, _dump_sparse_json(content), indent=4)

    entity_name = legacy_function_sources.read_model_entity_name(from_abs)
    from_folder = legacy_function_sources.derive_function_source_folder_name(from_rel_path, entity_name)
    to_folder = legacy_function_sources.derive_function_source_folder_name(to_rel_path, content.name)
    if from_folder and to_folder:
        from_dir_rel = Path(from_rel_path).parent.as_posix()
        to_dir_rel = Path(to_rel_path).parent.as_posix()
        from_folder_abs = safe_join(root, f"{from_dir_rel}/{from_folder}" if from_dir_rel != "." else from_folder)
        to_folder_abs = safe_join(root, f"{to_dir_rel}/{to_folder}" if to_dir_rel != "." else to_folder)
        if from_folder_abs.exists() and from_folder_abs.is_dir():
            legacy_function_sources.copy_directory(from_folder_abs, to_folder_abs)

    return PathMutationResult(fromAbsPath=str(from_abs), toAbsPath=str(to_abs))


def write_base_entity(rel_path: str, content: Any, solution_path: str | None) -> str:
    """Write base entity.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    content : Any
        content parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    str
        Computed return value."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    abs_path = safe_join(root, rel_path)
    validated = _validate_base_entities(content, path=rel_path)
    atomic_write_json(abs_path, _dump_sparse_json(validated), indent=4)
    return str(abs_path)


def regenerate_index(solution_path: str | None) -> dict[str, Any]:
    """Regenerate index.json for a solution using current model entities."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    entities = list_model_entities(solution_path)
    index = _build_index(sol=sol, entities=entities)
    index_path = root / "index.json"
    atomic_write_json(index_path, index, indent=4)
    return index


def regenerate_index_with_entities(solution_path: str | None) -> tuple[dict[str, Any], list[ModelEntityEntry]]:
    """Regenerate index.json and return the same scanned model entities."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    entities = list_model_entities(solution_path)
    index = _build_index(sol=sol, entities=entities)
    index_path = root / "index.json"
    atomic_write_json(index_path, index, indent=4)
    return index, entities


def _build_index(*, sol: Solution, entities: list[ModelEntityEntry]) -> dict[str, Any]:
    """Build in-memory index payload from model entities."""

    def zone_to_key(segment: str) -> str:
        m = re.match(r"^\d+\-([A-Za-z]+)", segment)
        slug = m.group(1).lower() if m else segment.lower()
        return f"{slug}Index"

    index: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entity in entities:
        try:
            rel_from_model = Path(entity.relPath).relative_to(Path(str(sol.modelPath))).as_posix()
        except Exception:
            rel_from_model = Path(entity.relPath).as_posix()
        zone_segment = rel_from_model.split("/")[0] if rel_from_model else "model"
        key = zone_to_key(zone_segment or "model")
        index.setdefault(key, {"entry": []})
        index[key]["entry"].append(
            {
                "locator": entity.locator.model_dump(mode="json"),
                "name": entity.name,
                "absPath": entity.absPath,
            }
        )

    for k in sorted(index.keys()):
        index[k]["entry"].sort(
            key=lambda e: (
                locator_sort_key(model_model.Locator.model_validate(e.get("locator"))),
                str(e.get("name") or ""),
            )
        )
    return index


def list_directory(dir_path: str | None) -> list[DirectoryEntry]:
    """List folders and `.dm8s` files in a directory.

    Parameters
    ----------
    dir_path : str | None
        Directory to inspect. Uses current working directory when omitted.

    Returns
    -------
    list[DirectoryEntry]
        Entry objects with `name`, `path`, and `type` (`dir`/`file`).

    Raises
    ------
    Datam8NotFoundError
        If the target directory does not exist.
    Datam8ValidationError
        If the target path exists but is not a directory."""
    target = Path(dir_path).expanduser() if dir_path else Path.cwd()
    if not target.exists():
        raise Datam8NotFoundError(message="Directory not found.", details={"path": str(target)})
    if not target.is_dir():
        raise Datam8ValidationError(message="Path is not a directory.", details={"path": str(target)})
    entries: list[DirectoryEntry] = []
    for e in os.scandir(target):
        if e.is_dir():
            entries.append(DirectoryEntry(name=e.name, path=str(Path(target, e.name)), type="dir"))
        elif e.is_file() and e.name.lower().endswith(".dm8s"):
            entries.append(DirectoryEntry(name=e.name, path=str(Path(target, e.name)), type="file"))
    entries.sort(key=lambda x: x.name.lower())
    return entries


def read_function_source(rel_path: str, source_file: str, solution_path: str | None, entity_name: str | None) -> str:
    """Read function source.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    source_file : str
        source_file parameter value.
    solution_path : str | None
        solution_path parameter value.
    entity_name : str | None
        entity_name parameter value.

    Returns
    -------
    str
        Computed return value."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = legacy_function_sources.resolve_safe_function_source_path(entity_dir, source_file)
        return abs_path.read_text(encoding="utf-8")

    folder_name, _fallback = legacy_function_sources.resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    abs_path = legacy_function_sources.resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=source_file, preferred_folder_name=folder_name)
    return abs_path.read_text(encoding="utf-8")


def write_function_source(
    rel_path: str,
    source_file: str,
    content: str,
    solution_path: str | None,
    entity_name: str | None,
) -> str:
    """Write function source.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    source_file : str
        source_file parameter value.
    content : str
        content parameter value.
    solution_path : str | None
        solution_path parameter value.
    entity_name : str | None
        entity_name parameter value.

    Returns
    -------
    str
        Computed return value."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = legacy_function_sources.resolve_safe_function_source_path(entity_dir, source_file)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(abs_path, content)
        return str(abs_path)

    legacy_function_sources.ensure_basename(source_file)
    folder_name, _fallback = legacy_function_sources.resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
    abs_path = safe_join(
        root,
        f"{dir_rel}/{folder_name}/{source_file}" if dir_rel != "." else f"{folder_name}/{source_file}",
    )
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(abs_path, content)
    legacy_function_sources.migrate_legacy_function_source_file(root=root, rel_path=rel_path, source_file=source_file, folder_name=folder_name)
    return str(abs_path)


def rename_function_source(
    rel_path: str,
    from_source: str,
    to_source: str,
    solution_path: str | None,
    entity_name: str | None,
) -> FunctionSourceRenameResult:
    """Rename function source.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    from_source : str
        from_source parameter value.
    to_source : str
        to_source parameter value.
    solution_path : str | None
        solution_path parameter value.
    entity_name : str | None
        entity_name parameter value.

    Returns
    -------
    FunctionSourceRenameResult
        Absolute source and destination paths and optional skipped marker."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)
    folder_name, _fallback = legacy_function_sources.resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)

    if isinstance(from_source, str) and "/" in from_source:
        from_abs = legacy_function_sources.resolve_safe_function_source_path(entity_dir, from_source)
    else:
        from_abs = legacy_function_sources.resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=from_source, preferred_folder_name=folder_name)

    if not (isinstance(to_source, str) and "/" in to_source):
        legacy_function_sources.ensure_basename(to_source)
        to_abs = safe_join(
            root,
            f"{dir_rel}/{folder_name}/{to_source}" if dir_rel != "." else f"{folder_name}/{to_source}",
        )
    else:
        to_abs = legacy_function_sources.resolve_safe_function_source_path(entity_dir, to_source)

    if not from_abs.exists():
        return FunctionSourceRenameResult(fromAbsPath=str(from_abs), toAbsPath=str(to_abs), skipped=True)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    if not (isinstance(to_source, str) and "/" in to_source):
        legacy_function_sources.migrate_legacy_function_source_file(root=root, rel_path=rel_path, source_file=to_source, folder_name=folder_name)
    return FunctionSourceRenameResult(fromAbsPath=str(from_abs), toAbsPath=str(to_abs))


def delete_function_source(rel_path: str, source_file: str, solution_path: str | None, entity_name: str | None) -> str:
    """Delete function source.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    source_file : str
        source_file parameter value.
    solution_path : str | None
        solution_path parameter value.
    entity_name : str | None
        entity_name parameter value.

    Returns
    -------
    str
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    dir_rel = Path(rel_path).parent.as_posix()
    entity_dir = root if dir_rel == "." else safe_join(root, dir_rel)

    if isinstance(source_file, str) and "/" in source_file:
        abs_path = legacy_function_sources.resolve_safe_function_source_path(entity_dir, source_file)
    else:
        folder_name, _fallback = legacy_function_sources.resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
        abs_path = legacy_function_sources.resolve_function_source_abs_path(root=root, rel_path=rel_path, source_file=source_file, preferred_folder_name=folder_name)

    if not abs_path.exists():
        raise Datam8NotFoundError(message="Script not found.", details={"source": source_file})
    abs_path.unlink()
    return str(abs_path)


def list_function_sources(
    rel_path: str, solution_path: str | None, entity_name: str | None, *, include_unreferenced: bool = True
) -> list[str]:
    """List function sources.

    Parameters
    ----------
    rel_path : str
        rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.
    entity_name : str | None
        entity_name parameter value.
    include_unreferenced : bool
        include_unreferenced parameter value.

    Returns
    -------
    list[str]
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
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

    folder_name, fallback = legacy_function_sources.resolve_function_source_folder_name(root=root, rel_path=rel_path, preferred_entity_name=entity_name)
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
    base_path: str | None,
    model_path: str | None,
    target: str,
) -> str:
    """Create a new minimal v2 solution workspace on disk.

    Parameters
    ----------
    solution_name : str
        Name of the solution and project folder.
    project_root : str
        Parent directory where the project will be created.
    base_path : str | None
        Optional base folder name (defaults to `Base`).
    model_path : str | None
        Optional model folder name (defaults to `Model`).
    target : str
        Generator target name for initial solution setup.

    Returns
    -------
    str
        Absolute path to the created `.dm8s` solution file.

    Raises
    ------
    Datam8ConflictError
        If project directory or solution file already exists.
    Datam8ValidationError
        If required input arguments are missing."""
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

    target_defaults = {
        "string": {"databricks": "string", "sqlserver": "nvarchar"},
        "int": {"databricks": "int", "sqlserver": "int"},
        "long": {"databricks": "bigint", "sqlserver": "bigint"},
        "double": {"databricks": "double", "sqlserver": "float"},
        "decimal": {"databricks": "decimal", "sqlserver": "decimal"},
        "datetime": {"databricks": "timestamp", "sqlserver": "datetime2"},
        "boolean": {"databricks": "boolean", "sqlserver": "bit"},
    }

    def _target_value(type_name: str) -> str:
        type_defaults = target_defaults.get(type_name, {})
        return type_defaults.get(target, type_defaults.get("databricks", type_name))

    default_data_types = [
        {
            "name": "string",
            "displayName": "Unicode String",
            "hasCharLen": True,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("string")},
        },
        {
            "name": "int",
            "displayName": "Integer (32 bit)",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("int")},
        },
        {
            "name": "long",
            "displayName": "Integer (64 bit)",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("long")},
        },
        {
            "name": "double",
            "displayName": "Double",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("double")},
        },
        {
            "name": "decimal",
            "displayName": "Decimal",
            "hasCharLen": False,
            "hasPrecision": True,
            "hasScale": True,
            "targets": {target: _target_value("decimal")},
        },
        {
            "name": "datetime",
            "displayName": "DateTime",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("datetime")},
        },
        {
            "name": "boolean",
            "displayName": "Boolean",
            "hasCharLen": False,
            "hasPrecision": False,
            "hasScale": False,
            "targets": {target: _target_value("boolean")},
        },
    ]

    base_files: dict[str, Any] = {
        "AttributeTypes": {"type": "attributeTypes", "attributeTypes": default_attribute_types},
        "DataTypes": {"type": "dataTypes", "dataTypes": default_data_types},
        "DataSourceTypes": {
            "type": "dataSourceTypes",
            "dataSourceTypes": [
                {
                    "name": "Generic",
                    "displayName": "Generic",
                    "dataTypeMapping": [{"sourceType": "string", "targetType": "string"}],
                    "connectionProperties": [],
                }
            ],
        },
        "DataSources": {"type": "dataSources", "dataSources": []},
        "DataProducts": {
            "type": "dataProducts",
            "dataProducts": [{"name": "Default", "dataModules": [{"name": "Default"}]}],
        },
        "Zones": {
            "type": "zones",
            "zones": [{"name": "Raw", "targetName": "Raw", "displayName": "Raw", "localFolderName": "010-Raw"}],
        },
        "Properties": {"type": "properties", "properties": []},
        "PropertyValues": {"type": "propertyValues", "propertyValues": []},
    }

    atomic_write_json(solution_file_path, solution_content, indent=4)
    for name, content in base_files.items():
        atomic_write_json(base_dir / f"{name}.json", content, indent=4)

    return str(solution_file_path)


def rename_folder(from_folder_rel_path: str, to_folder_rel_path: str, solution_path: str | None) -> PathMutationResult:
    """Rename folder.

    Parameters
    ----------
    from_folder_rel_path : str
        from_folder_rel_path parameter value.
    to_folder_rel_path : str
        to_folder_rel_path parameter value.
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    PathMutationResult
        Absolute source and destination folder paths."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    from_abs = safe_join(root, from_folder_rel_path)
    to_abs = safe_join(root, to_folder_rel_path)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    from_abs.rename(to_abs)
    return PathMutationResult(fromAbsPath=str(from_abs), toAbsPath=str(to_abs))


def refactor_properties(
    *,
    solution_path: str | None,
    property_renames: list[dict[str, str]],
    value_renames: list[dict[str, str]],
    deleted_properties: list[str],
    deleted_values: list[dict[str, str]],
) -> RefactorPropertiesResult:
    """Apply property/value rename and delete operations across workspace JSON.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    property_renames : list[dict[str, str]]
        Rename operations (`oldName` -> `newName`) for property keys.
    value_renames : list[dict[str, str]]
        Rename operations for property values.
    deleted_properties : list[str]
        Property names to remove.
    deleted_values : list[dict[str, str]]
        Specific property/value pairs to remove.

    Returns
    -------
    RefactorPropertiesResult
        Summary with the number of updated files."""
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

    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir
    candidate_paths = [
        *_iter_json_files(root, str(sol.basePath)),
        *_iter_json_files(root, str(sol.modelPath), ignore=[".properties.json"]),
    ]
    updated = 0

    for abs_path in candidate_paths:
        changed, value = transform_node(_read_json_file(abs_path))
        if changed:
            atomic_write_json(abs_path, value, indent=4)
            updated += 1

    return RefactorPropertiesResult(updatedFiles=updated)
