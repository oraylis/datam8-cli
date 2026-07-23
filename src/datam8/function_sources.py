# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from datam8 import model
from datam8_model import base as b


def _require_contained(path: Path, root: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"{label} resolves outside its allowed root")
    return resolved_path


def normalize_source_path(source: str) -> Path:
    normalized = source.strip().replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    posix_path = PurePosixPath(normalized)

    if (
        not normalized
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or posix_path.is_absolute()
    ):
        raise ValueError("Function source path must be relative")

    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("Function source path contains an invalid segment")

    return Path(*parts)


def entity_function_root(
    datam8_model: model.Model,
    locator: model.Locator | str,
    *,
    require_entity: bool = True,
) -> Path:
    parsed = model.Locator.from_path(locator) if isinstance(locator, str) else locator
    if parsed.entityType != b.EntityType.MODEL_ENTITIES.value or not parsed.entityName:
        raise ValueError("Locator must point to a model entity")

    if require_entity:
        datam8_model.get_entity_by_locator(parsed)

    model_root = datam8_model.get_base_path_for_entity_type(
        b.EntityType.MODEL_ENTITIES
    ).resolve()
    candidate = model_root.joinpath(*parsed.folders, parsed.entityName)
    return _require_contained(candidate, model_root, label="Entity function root")


def source_path(
    datam8_model: model.Model,
    locator: model.Locator | str,
    source: str,
) -> Path:
    root = entity_function_root(datam8_model, locator)
    return _require_contained(
        root / normalize_source_path(source),
        root,
        label="Function source path",
    )


def read_source(datam8_model: model.Model, locator: str, source: str) -> str:
    path = source_path(datam8_model, locator, source)
    if not path.is_file():
        raise FileNotFoundError("Function source not found")
    return path.read_text(encoding="utf-8")


def write_source(
    datam8_model: model.Model,
    locator: str,
    source: str,
    content: str,
) -> None:
    path = source_path(datam8_model, locator, source)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _prune_empty_parents(path: Path, root: Path) -> None:
    current = path.parent
    while current != root and current.is_relative_to(root):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def delete_source(datam8_model: model.Model, locator: str, source: str) -> None:
    root = entity_function_root(datam8_model, locator)
    path = source_path(datam8_model, locator, source)
    if not path.is_file():
        raise FileNotFoundError("Function source not found")
    path.unlink()
    _prune_empty_parents(path, root)


def rename_source(
    datam8_model: model.Model,
    locator: str,
    from_source: str,
    to_source: str,
) -> None:
    root = entity_function_root(datam8_model, locator)
    from_path = source_path(datam8_model, locator, from_source)
    to_path = source_path(datam8_model, locator, to_source)

    if not from_path.is_file():
        raise FileNotFoundError("Function source not found")
    if to_path.exists() and to_path != from_path:
        raise FileExistsError("Target function source already exists")

    to_path.parent.mkdir(parents=True, exist_ok=True)
    from_path.replace(to_path)
    _prune_empty_parents(from_path, root)


@dataclass(frozen=True)
class FunctionDirectoryMove:
    source: Path
    target: Path
    additional_moves: tuple[tuple[Path, Path], ...] = ()

    def rollback(self) -> None:
        moves = [(self.source, self.target), *self.additional_moves]
        for source, target in reversed(moves):
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                target.rename(source)


def move_entity_directory(
    datam8_model: model.Model,
    from_locator: str,
    to_locator: str,
) -> FunctionDirectoryMove | None:
    from_parsed = model.Locator.from_path(from_locator)
    to_parsed = model.Locator.from_path(to_locator)
    if from_parsed.entityType != to_parsed.entityType:
        return None

    locator_pairs: list[tuple[model.Locator, model.Locator]] = []
    if from_parsed.entityType == b.EntityType.MODEL_ENTITIES.value:
        if not from_parsed.entityName:
            return None
        if to_parsed.entityName is None:
            to_parsed.entityName = from_parsed.entityName
        locator_pairs.append((from_parsed, to_parsed))
    elif (
        from_parsed.entityType == b.EntityType.FOLDERS.value
        and from_parsed.entityName
        and to_parsed.entityName
    ):
        source_folder = [*from_parsed.folders, from_parsed.entityName]
        target_folder = [*to_parsed.folders, to_parsed.entityName]
        for wrapper in datam8_model.get_entities_for_locator(from_parsed):
            locator = wrapper.locator
            if locator.entityType != b.EntityType.MODEL_ENTITIES.value:
                continue
            locator_pairs.append(
                (
                    locator,
                    model.Locator(
                        entityType=b.EntityType.MODEL_ENTITIES.value,
                        folders=[
                            *target_folder,
                            *locator.folders[len(source_folder) :],
                        ],
                        entityName=locator.entityName,
                    ),
                )
            )
    else:
        return None

    path_pairs = [
        (
            entity_function_root(datam8_model, source_locator),
            entity_function_root(datam8_model, target_locator, require_entity=False),
        )
        for source_locator, target_locator in locator_pairs
    ]
    path_pairs = [
        (source, target)
        for source, target in path_pairs
        if source != target and source.exists()
    ]
    if not path_pairs:
        return None

    targets = [target for _, target in path_pairs]
    if len(set(targets)) != len(targets):
        raise ValueError("Function directory move produces duplicate targets")
    for _, target in path_pairs:
        if target.exists():
            raise FileExistsError(f"Target function directory already exists: {target}")

    completed: list[tuple[Path, Path]] = []
    try:
        for source, target in path_pairs:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            completed.append((source, target))
    except Exception:
        for source, target in reversed(completed):
            source.parent.mkdir(parents=True, exist_ok=True)
            target.rename(source)
        raise

    source, target = completed[0]
    return FunctionDirectoryMove(
        source=source,
        target=target,
        additional_moves=tuple(completed[1:]),
    )
