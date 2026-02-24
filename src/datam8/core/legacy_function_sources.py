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
import re
from pathlib import Path
from typing import Any

from datam8.core.errors import Datam8ValidationError
from datam8.core.paths import safe_join
from datam8_model import model as model_model


def sanitize_path_segment(value: str) -> str:
    """Normalize a path segment for legacy function-source folders."""
    trimmed = str(value or "").strip()
    return trimmed.replace("\\", "_").replace("/", "_").replace("\0", "")


def parse_entity_name_from_model_entity(content: Any) -> str:
    """Extract `name` from a model entity payload."""
    if isinstance(content, model_model.ModelEntity):
        return content.name.strip()
    if not isinstance(content, dict):
        return ""
    name = content.get("name")
    return name.strip() if isinstance(name, str) else ""


def derive_function_source_folder_name(rel_path: str, entity_name: str) -> str:
    """Derive a folder name for function source files."""
    safe = sanitize_path_segment(entity_name)
    if safe:
        return safe
    return sanitize_path_segment(Path(rel_path).stem)


def read_model_entity_name(abs_path: Path) -> str:
    """Best-effort read of a model entity name from a JSON file."""
    try:
        raw = abs_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return ""
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"].strip()
    return ""


def merge_directories(from_abs: Path, to_abs: Path) -> None:
    """Move files from one directory into another without overwriting files."""
    to_abs.mkdir(parents=True, exist_ok=True)
    for entry in from_abs.iterdir():
        src = entry
        dst = to_abs / entry.name
        if entry.is_dir():
            merge_directories(src, dst)
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


def copy_directory(src: Path, dst: Path) -> None:
    """Copy directory tree without overwriting existing files."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        source_path = entry
        target_path = dst / entry.name
        if entry.is_dir():
            copy_directory(source_path, target_path)
            continue
        if entry.is_file():
            if target_path.exists():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(source_path.read_bytes())


def ensure_function_source_folder_name(
    *,
    root: Path,
    rel_path: str,
    prev_entity_name: str,
    next_entity_name: str,
) -> None:
    """Rename legacy function-source folders when entity names change."""
    dir_rel = Path(rel_path).parent.as_posix()
    from_name = derive_function_source_folder_name(rel_path, prev_entity_name)
    to_name = derive_function_source_folder_name(rel_path, next_entity_name)
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
    merge_directories(from_abs, to_abs)


def move_function_source_folder(*, root: Path, from_rel_path: str, to_rel_path: str, entity_name: str) -> None:
    """Move derived function-source folder when entity files are moved."""
    from_dir = Path(from_rel_path).parent.as_posix()
    to_dir = Path(to_rel_path).parent.as_posix()
    folder_name = derive_function_source_folder_name(from_rel_path, entity_name)
    if not folder_name:
        return
    from_abs = safe_join(root, f"{from_dir}/{folder_name}" if from_dir != "." else folder_name)
    if not from_abs.exists():
        return
    to_abs = safe_join(root, f"{to_dir}/{folder_name}" if to_dir != "." else folder_name)
    to_abs.parent.mkdir(parents=True, exist_ok=True)
    if to_abs.exists():
        merge_directories(from_abs, to_abs)
        return
    from_abs.rename(to_abs)


def ensure_basename(value: str) -> None:
    """Validate source-file basename for function scripts."""
    if not value or Path(value).name != value or ".." in value:
        raise Datam8ValidationError(message="Invalid function source filename.", details={"value": value})


def resolve_safe_function_source_path(entity_dir: Path, source_file: str) -> Path:
    """Resolve a nested relative function-source path safely."""
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


def resolve_function_source_folder_name(
    *,
    root: Path,
    rel_path: str,
    preferred_entity_name: str | None = None,
) -> tuple[str, str]:
    """Resolve primary and fallback folder names for function sources."""
    entity_abs = safe_join(root, rel_path)
    entity_name = (preferred_entity_name or "").strip() or (
        read_model_entity_name(entity_abs) if entity_abs.exists() else ""
    )
    folder_name = derive_function_source_folder_name(rel_path, entity_name)
    fallback_folder_name = sanitize_path_segment(Path(rel_path).stem)
    return folder_name, fallback_folder_name


def resolve_function_source_abs_path(
    *,
    root: Path,
    rel_path: str,
    source_file: str,
    preferred_folder_name: str | None = None,
) -> Path:
    """Resolve legacy-compatible function source absolute path."""
    ensure_basename(source_file)
    dir_rel = Path(rel_path).parent.as_posix()
    if preferred_folder_name:
        folder_name = preferred_folder_name
        fallback_folder_name = sanitize_path_segment(Path(rel_path).stem)
    else:
        folder_name, fallback_folder_name = resolve_function_source_folder_name(root=root, rel_path=rel_path)

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


def migrate_legacy_function_source_file(*, root: Path, rel_path: str, source_file: str, folder_name: str) -> None:
    """Move legacy adjacent source files into the derived source folder."""
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


def migrate_legacy_function_sources(*, root: Path, rel_path: str, content: Any) -> None:
    """Migrate all referenced function-source files for one model entity."""
    entity_name = parse_entity_name_from_model_entity(content)
    folder_name, _fallback = resolve_function_source_folder_name(
        root=root,
        rel_path=rel_path,
        preferred_entity_name=entity_name,
    )
    sources: list[str] = []
    if isinstance(content, model_model.ModelEntity):
        for transform in content.transformations:
            if str(transform.kind.value) != "function":
                continue
            if transform.function and isinstance(transform.function.source, str) and transform.function.source.strip():
                sources.append(transform.function.source.strip())
    elif isinstance(content, dict):
        transforms = content.get("transformations")
        if not isinstance(transforms, list):
            return
        for transform in transforms:
            if not isinstance(transform, dict) or transform.get("kind") != "function":
                continue
            function = transform.get("function")
            if not isinstance(function, dict):
                continue
            source = function.get("source")
            if isinstance(source, str) and source.strip():
                sources.append(source.strip())
    else:
        return
    for source in sources:
        try:
            ensure_basename(source)
            migrate_legacy_function_source_file(
                root=root,
                rel_path=rel_path,
                source_file=source,
                folder_name=folder_name,
            )
        except Exception:
            continue
