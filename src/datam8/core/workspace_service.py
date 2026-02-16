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

from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

from pydantic import BaseModel

from datam8.core import workspace_io
from datam8.core.errors import Datam8ValidationError
from datam8.core.lock import SolutionLock
from datam8.core.parse_utils import parse_duration_seconds
from datam8_model import folder as folder_model
from datam8_model.solution import Solution


class SolutionFullSnapshot(BaseModel):
    """Combined solution metadata and workspace entities."""

    solutionPath: str
    solution: Solution
    baseEntities: list[workspace_io.BaseEntityEntry]
    modelEntities: list[workspace_io.ModelEntityEntry]
    folderEntities: list[workspace_io.FolderEntityEntry]


class RenameModelFolderResult(BaseModel):
    """Result payload for model-folder rename operations."""

    fromAbsPath: str
    toAbsPath: str
    entities: list[workspace_io.ModelEntityEntry]
    index: dict[str, Any]


def list_model_entities(solution_path: str | None) -> list[workspace_io.ModelEntityEntry]:
    """List model entities."""
    return workspace_io.list_model_entities(solution_path)


def list_base_entities(solution_path: str | None) -> list[workspace_io.BaseEntityEntry]:
    """List base entities."""
    return workspace_io.list_base_entities(solution_path)


def list_folder_entities(solution_path: str | None) -> list[workspace_io.FolderEntityEntry]:
    """List folder metadata entities."""
    return workspace_io.list_folder_entities(solution_path)


def get_solution_full_snapshot(solution_path: str | None) -> SolutionFullSnapshot:
    """Build the full workspace snapshot used by API and CLI."""
    resolved, sol = workspace_io.read_solution(solution_path)
    return SolutionFullSnapshot(
        solutionPath=str(resolved.solution_file),
        solution=sol,
        baseEntities=list_base_entities(solution_path),
        modelEntities=list_model_entities(solution_path),
        folderEntities=list_folder_entities(solution_path),
    )


def create_model_entity(
    *,
    rel_path: str,
    name: str | None,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Create model entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.create_model_entity(rel_path, name=name, solution_path=solution_path),
    )


def save_model_entity(
    *,
    rel_path: str,
    content: Any,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Save model entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.write_model_entity(rel_path, content, solution_path),
    )


def delete_model_entity(
    *,
    rel_path: str,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Delete model entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.delete_model_entity(rel_path, solution_path),
    )


def move_model_entity(
    *,
    from_rel_path: str,
    to_rel_path: str,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> workspace_io.PathMutationResult:
    """Move model entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.move_model_entity(from_rel_path, to_rel_path, solution_path),
    )


def duplicate_model_entity(
    *,
    from_rel_path: str,
    to_rel_path: str,
    solution_path: str | None,
    new_name: str | None = None,
    new_id: int | None = None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> workspace_io.PathMutationResult:
    """Duplicate model entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.duplicate_model_entity(
            from_rel_path,
            to_rel_path,
            solution_path=solution_path,
            new_name=new_name,
            new_id=new_id,
        ),
    )


def rename_model_folder(
    *,
    from_folder_rel_path: str,
    to_folder_rel_path: str,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> RenameModelFolderResult:
    """Rename model folder and refresh index/entities via one shared operation."""

    def _operation() -> RenameModelFolderResult:
        result = workspace_io.rename_folder(from_folder_rel_path, to_folder_rel_path, solution_path)
        index, entities = workspace_io.regenerate_index_with_entities(solution_path)
        return RenameModelFolderResult(
            fromAbsPath=result.fromAbsPath,
            toAbsPath=result.toAbsPath,
            entities=entities,
            index=index,
        )

    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=_operation,
    )


def save_base_entity(
    *,
    rel_path: str,
    content: Any,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Save base entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.write_base_entity(rel_path, content, solution_path),
    )


def delete_base_entity(
    *,
    rel_path: str,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Delete base entity with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.delete_base_entity(rel_path, solution_path),
    )


def regenerate_index(
    *,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> dict[str, Any]:
    """Regenerate index with shared lock semantics."""
    return _run_with_lock(
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
        operation=lambda: workspace_io.regenerate_index(solution_path),
    )


def read_folder_metadata(*, rel_path: str, solution_path: str | None) -> folder_model.Folder:
    """Read folder metadata from a `.properties.json` file."""
    _validate_folder_metadata_rel_path(rel_path)
    return workspace_io.read_folder_metadata(rel_path, solution_path)


def save_folder_metadata(
    *,
    rel_path: str,
    content: Any,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Save folder metadata to a `.properties.json` file."""
    _validate_folder_metadata_rel_path(rel_path)
    return save_model_entity(
        rel_path=rel_path,
        content=content,
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )


def delete_folder_metadata(
    *,
    rel_path: str,
    solution_path: str | None,
    lock_timeout: str | int | float | None = None,
    no_lock: bool = False,
) -> str:
    """Delete folder metadata `.properties.json` file."""
    _validate_folder_metadata_rel_path(rel_path)
    return delete_model_entity(
        rel_path=rel_path,
        solution_path=solution_path,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )


def _run_with_lock[TResult](
    *,
    solution_path: str | None,
    lock_timeout: str | int | float | None,
    no_lock: bool,
    operation: Callable[[], TResult],
) -> TResult:
    resolved, _sol = workspace_io.read_solution(solution_path)
    timeout_seconds = _parse_lock_timeout_seconds(lock_timeout)
    context = nullcontext() if no_lock else SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=timeout_seconds,
    )
    with context:
        return operation()


def _validate_folder_metadata_rel_path(rel_path: str) -> None:
    normalized = (rel_path or "").replace("\\", "/")
    if normalized.endswith(".properties.json"):
        return
    raise Datam8ValidationError(
        message="Folder metadata relPath must point to a '.properties.json' file.",
        details={"relPath": rel_path},
    )


def _parse_lock_timeout_seconds(lock_timeout: str | int | float | None) -> float:
    if isinstance(lock_timeout, (int, float)):
        return float(lock_timeout)
    if isinstance(lock_timeout, str) and lock_timeout.strip():
        return parse_duration_seconds(lock_timeout)
    return parse_duration_seconds("10s")
