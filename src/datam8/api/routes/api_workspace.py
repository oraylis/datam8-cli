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

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from datam8.cmd.generate import GenerateResult, run_generation
from datam8.core import duration, indexing, workspace_io
from datam8.core import refactor as refactor_core
from datam8.core import search as search_core
from datam8.core.lock import SolutionLock

from .common import lock_timeout_seconds
from .response_models import (
    BaseEntitiesResponse,
    BaseEntityResponse,
    ContentResponse,
    DirectoryEntryResponse,
    EntriesResponse,
    FunctionSourceRenameResponse,
    IndexRegenerateResponse,
    IndexShowResponse,
    IndexValidateResponse,
    MessageWithPathResponse,
    ModelEntitiesResponse,
    ModelEntityResponse,
    MoveEntityResponse,
    RefactorPropertiesResponse,
    RefactorResultResponse,
    RefactorRunResponse,
    RenameFolderResponse,
    ScriptListResponse,
    SearchEntitiesResponse,
    SearchTextResponse,
)

router = APIRouter()


class SaveEntityBody(BaseModel):
    """Request body for saving model/base entities."""

    relPath: str
    content: Any
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class DeleteEntityBody(BaseModel):
    """Request body for deleting model/base entities."""

    relPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class MoveEntityBody(BaseModel):
    """Request body for moving model entities."""

    fromRelPath: str
    toRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class RenameFolderBody(BaseModel):
    """Request body for renaming model folders."""

    fromFolderRelPath: str
    toFolderRelPath: str
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class RefactorPropertiesBody(BaseModel):
    """Request body for property/value refactoring."""

    solutionPath: str | None = None
    propertyRenames: list[dict[str, str]] = Field(default_factory=list)
    valueRenames: list[dict[str, str]] = Field(default_factory=list)
    deletedProperties: list[str] = Field(default_factory=list)
    deletedValues: list[dict[str, str]] = Field(default_factory=list)
    lockTimeout: str | None = None
    noLock: bool | None = None


class GenerateBody(BaseModel):
    """Request body for synchronous generation."""

    solutionPath: str
    target: str
    logLevel: str | None = None
    cleanOutput: bool | None = None
    payloads: list[str] | None = None
    lazy: bool | None = None


class IndexRegenerateBody(BaseModel):
    """Request body for index regeneration."""

    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class FunctionSourceSaveBody(BaseModel):
    """Request body for writing function sources."""

    relPath: str
    source: str
    entityName: str | None = None
    content: str
    solutionPath: str | None = None


class FunctionSourceRenameBody(BaseModel):
    """Request body for renaming function sources."""

    relPath: str
    fromSource: str
    toSource: str
    entityName: str | None = None
    solutionPath: str | None = None


class RefactorKeysBody(BaseModel):
    """Request body for key refactoring."""

    solutionPath: str | None = None
    mapping: dict[str, str]
    apply: bool = False


class RefactorValuesBody(BaseModel):
    """Request body for value refactoring."""

    solutionPath: str | None = None
    old: str
    new: str
    key: str | None = None
    apply: bool = False


class RefactorEntityIdBody(BaseModel):
    """Request body for entity ID refactoring."""

    solutionPath: str | None = None
    old: int
    new: int
    apply: bool = False


@router.get("/model/entities")
async def model_entities(path: str | None = Query(None)) -> ModelEntitiesResponse:
    """List model entities for the active solution."""
    entities = [
        ModelEntityResponse.model_validate(entity.model_dump())
        for entity in workspace_io.list_model_entities(path)
    ]
    return ModelEntitiesResponse(count=len(entities), entities=entities)


@router.post("/model/entities")
async def model_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.write_model_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            abs_path = workspace_io.write_model_entity(
                body.relPath,
                body.content,
                body.solutionPath,
            )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/model/entities")
async def model_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.delete_model_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            abs_path = workspace_io.delete_model_entity(body.relPath, body.solutionPath)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.post("/model/entities/move")
async def model_entities_move(body: MoveEntityBody) -> MoveEntityResponse:
    """Move a model entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.move_model_entity(body.fromRelPath, body.toRelPath, body.solutionPath)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            result = workspace_io.move_model_entity(
                body.fromRelPath,
                body.toRelPath,
                body.solutionPath,
            )
    return MoveEntityResponse(
        message="moved",
        **{"from": result.fromAbsPath, "to": result.toAbsPath},
    )


@router.post("/model/folder/rename")
async def model_folder_rename(body: RenameFolderBody) -> RenameFolderResponse:
    """Rename a model folder and regenerate index."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.rename_folder(
            body.fromFolderRelPath,
            body.toFolderRelPath,
            body.solutionPath,
        )
        _, model_entities = workspace_io.regenerate_index_with_entities(body.solutionPath)
        entities = [
            ModelEntityResponse.model_validate(entity.model_dump())
            for entity in model_entities
        ]
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            result = workspace_io.rename_folder(
                body.fromFolderRelPath,
                body.toFolderRelPath,
                body.solutionPath,
            )
            _, model_entities = workspace_io.regenerate_index_with_entities(body.solutionPath)
            entities = [
                ModelEntityResponse.model_validate(entity.model_dump())
                for entity in model_entities
            ]
    return RenameFolderResponse(
        message="renamed",
        entities=entities,
        **{"from": result.fromAbsPath, "to": result.toAbsPath},
    )


@router.post("/refactor/properties")
async def refactor_properties_route(body: RefactorPropertiesBody) -> RefactorPropertiesResponse:
    """Refactor properties and values across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        result = workspace_io.refactor_properties(
            solution_path=body.solutionPath,
            property_renames=body.propertyRenames,
            value_renames=body.valueRenames,
            deleted_properties=body.deletedProperties,
            deleted_values=body.deletedValues,
        )
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            result = workspace_io.refactor_properties(
                solution_path=body.solutionPath,
                property_renames=body.propertyRenames,
                value_renames=body.valueRenames,
                deleted_properties=body.deletedProperties,
                deleted_values=body.deletedValues,
            )
    return RefactorPropertiesResponse(message="refactored", updatedFiles=result.updatedFiles)


@router.post("/index/regenerate")
async def index_regenerate(body: IndexRegenerateBody) -> IndexRegenerateResponse:
    """Regenerate and return solution index."""
    solution_path = body.solutionPath
    resolved, _sol = workspace_io.read_solution(solution_path)
    if body.noLock:
        index = workspace_io.regenerate_index(solution_path)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            index = workspace_io.regenerate_index(solution_path)
    return IndexRegenerateResponse(message="index regenerated", index=index)


@router.get("/index/show")
async def index_show(path: str | None = Query(None)) -> IndexShowResponse:
    """Return current solution index."""
    return IndexShowResponse(index=indexing.read_index(path))


@router.get("/index/validate")
async def index_validate_route(path: str | None = Query(None)) -> IndexValidateResponse:
    """Return validation report for current index."""
    return IndexValidateResponse(report=indexing.validate_index(path))


@router.post("/generate", response_model=GenerateResult)
async def generator_run(body: GenerateBody) -> GenerateResult:
    """Execute generator synchronously."""
    return await run_in_threadpool(
        run_generation,
        solution_path=Path(body.solutionPath),
        target=body.target,
        log_level=body.logLevel or "info",
        clean_output=bool(body.cleanOutput),
        payloads=body.payloads or [],
        generate_all=False,
        lazy=bool(body.lazy),
    )


@router.get("/base/entities")
async def base_entities(path: str | None = Query(None)) -> BaseEntitiesResponse:
    """List base entities for the active solution."""
    entities = [
        BaseEntityResponse.model_validate(entity.model_dump())
        for entity in workspace_io.list_base_entities(path)
    ]
    return BaseEntitiesResponse(count=len(entities), entities=entities)


@router.post("/base/entities")
async def base_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a base entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.write_base_entity(body.relPath, body.content, body.solutionPath)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            abs_path = workspace_io.write_base_entity(body.relPath, body.content, body.solutionPath)
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/base/entities")
async def base_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a base entity file."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.noLock:
        abs_path = workspace_io.delete_base_entity(body.relPath, body.solutionPath)
    else:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=lock_timeout_seconds(body.model_dump()),
        ):
            abs_path = workspace_io.delete_base_entity(body.relPath, body.solutionPath)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.get("/fs/list")
async def fs_list(path: str | None = Query(None)) -> EntriesResponse:
    """List directory entries inside the active workspace."""
    entries = [DirectoryEntryResponse.model_validate(entry.model_dump()) for entry in workspace_io.list_directory(path)]
    return EntriesResponse(entries=entries)


@router.get("/model/function/source")
async def model_function_source_get(
    relPath: str = Query(""),
    source: str = Query(""),
    entityName: str | None = Query(None),
    solutionPath: str | None = Query(None),
) -> ContentResponse:
    """Read model function source content."""
    content = workspace_io.read_function_source(relPath, source, solutionPath, entityName)
    return ContentResponse(content=content)


@router.post("/model/function/source")
async def model_function_source_save(body: FunctionSourceSaveBody) -> MessageWithPathResponse:
    """Save model function source content."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=duration.parse_duration_seconds("10s"),
    ):
        abs_path = workspace_io.write_function_source(
            body.relPath,
            body.source,
            body.content,
            body.solutionPath,
            body.entityName,
        )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.post("/model/function/rename")
async def model_function_source_rename(body: FunctionSourceRenameBody) -> FunctionSourceRenameResponse:
    """Rename model function source key."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=duration.parse_duration_seconds("10s"),
    ):
        result = workspace_io.rename_function_source(
            body.relPath,
            body.fromSource,
            body.toSource,
            body.solutionPath,
            body.entityName,
        )
    return FunctionSourceRenameResponse(
        message="renamed",
        fromAbsPath=result.fromAbsPath,
        toAbsPath=result.toAbsPath,
        skipped=result.skipped,
    )


@router.get("/script/list")
async def script_list(path: str = Query(...), solutionPath: str | None = Query(None)) -> ScriptListResponse:
    """List script/function source names for an entity."""
    scripts = workspace_io.list_function_sources(
        path,
        solutionPath,
        None,
        include_unreferenced=True,
    )
    return ScriptListResponse(count=len(scripts), scripts=scripts)


@router.delete("/script/delete")
async def script_delete(
    path: str = Query(...),
    source: str = Query(...),
    solutionPath: str | None = Query(None),
) -> MessageWithPathResponse:
    """Delete a script/function source file."""
    resolved, _sol = workspace_io.read_solution(solutionPath)
    with SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=duration.parse_duration_seconds("10s"),
    ):
        abs_path = workspace_io.delete_function_source(path, source, solutionPath, None)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.get("/search/entities")
async def search_entities_route(q: str = Query(...), path: str | None = Query(None)) -> SearchEntitiesResponse:
    """Search entities by metadata fields."""
    result = search_core.search_entities(solution_path=path, query=q)
    return SearchEntitiesResponse(count=result["count"], entities=result["entities"])


@router.get("/search/text")
async def search_text_route(q: str = Query(...), path: str | None = Query(None)) -> SearchTextResponse:
    """Search raw text across solution files."""
    result = search_core.search_text(solution_path=path, pattern=q)
    return SearchTextResponse(
        count=result["count"],
        total=result["total"],
        matches=result["matches"],
    )


@router.post("/refactor/keys")
async def refactor_keys_route(body: RefactorKeysBody) -> RefactorRunResponse:
    """Refactor property keys across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=duration.parse_duration_seconds("10s"),
        ):
            result = refactor_core.refactor_keys(
                solution_path=body.solutionPath,
                renames=body.mapping,
                apply=True,
            )
    else:
        result = refactor_core.refactor_keys(
            solution_path=body.solutionPath,
            renames=body.mapping,
            apply=False,
        )
    return RefactorRunResponse(
        message="refactored",
        dryRun=not body.apply,
        result=RefactorResultResponse.model_validate(result),
    )


@router.post("/refactor/values")
async def refactor_values_route(body: RefactorValuesBody) -> RefactorRunResponse:
    """Refactor property values across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=duration.parse_duration_seconds("10s"),
        ):
            result = refactor_core.refactor_values(
                solution_path=body.solutionPath,
                old=body.old,
                new=body.new,
                key=body.key,
                apply=True,
            )
    else:
        result = refactor_core.refactor_values(
            solution_path=body.solutionPath,
            old=body.old,
            new=body.new,
            key=body.key,
            apply=False,
        )
    return RefactorRunResponse(
        message="refactored",
        dryRun=not body.apply,
        result=RefactorResultResponse.model_validate(result),
    )


@router.post("/refactor/entity-id")
async def refactor_entity_id_route(body: RefactorEntityIdBody) -> RefactorRunResponse:
    """Refactor entity IDs across model entities."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    if body.apply:
        with SolutionLock(
            resolved.root_dir / ".datam8.lock",
            timeout_seconds=duration.parse_duration_seconds("10s"),
        ):
            result = refactor_core.refactor_entity_id(
                solution_path=body.solutionPath,
                old=body.old,
                new=body.new,
                apply=True,
            )
    else:
        result = refactor_core.refactor_entity_id(
            solution_path=body.solutionPath,
            old=body.old,
            new=body.new,
            apply=False,
        )
    return RefactorRunResponse(
        message="refactored",
        dryRun=not body.apply,
        result=RefactorResultResponse.model_validate(result),
    )
