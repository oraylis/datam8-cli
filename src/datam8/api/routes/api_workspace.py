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

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from datam8 import config, factory, generate, logging, model, opts
from datam8.core import refactor as refactor_core
from datam8.core import search as search_core
from datam8.core import workspace_io, workspace_service
from datam8.core.entity_resolution import resolve_model_entity
from datam8.core.errors import Datam8ValidationError
from datam8.core.jsonops import merge_patch, set_by_pointer
from datam8.core.lock import SolutionLock
from datam8.core.parse_utils import parse_duration_seconds
from datam8.core.solution_index import read_index, validate_index
from datam8_model import base as b
from datam8_model import model as model_model

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
    JsonDocumentResponse,
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
    ValidationStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _dump_sparse_json(model: BaseModel) -> Any:
    return model.model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=True,
    )


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
    propertyRenames: list[dict[str, str]] = Field(default_factory=dict)
    valueRenames: list[dict[str, str]] = Field(default_factory=dict)
    deletedProperties: list[str] = Field(default_factory=list)
    deletedValues: list[dict[str, str]] = Field(default_factory=dict)
    lockTimeout: str | None = None
    noLock: bool | None = None


class GenerateBody(BaseModel):
    """Request body for synchronous generation."""

    target: str | None = None
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


class SetByPointerBody(BaseModel):
    """Request body for JSON pointer set operations."""

    relPath: str
    pointer: str
    value: Any
    createMissing: bool = True
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class PatchEntityBody(BaseModel):
    """Request body for JSON merge-patch operations."""

    relPath: str
    patch: Any
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class ModelEntityCreateBody(BaseModel):
    """Request body for creating model entities."""

    relPath: str
    name: str | None = None
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class ModelEntitySelectorBody(BaseModel):
    """Request body for model-entity selector operations."""

    selector: str
    by: str = "auto"
    solutionPath: str | None = None


class ModelEntitySetBody(BaseModel):
    """Request body for setting a JSON pointer in model entity."""

    selector: str
    by: str = "auto"
    pointer: str
    value: Any
    createMissing: bool = True
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class ModelEntityPatchBody(BaseModel):
    """Request body for merge-patching a model entity."""

    selector: str
    by: str = "auto"
    patch: Any
    solutionPath: str | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


class DuplicateEntityBody(BaseModel):
    """Request body for duplicating model entities."""

    fromRelPath: str
    toRelPath: str
    solutionPath: str | None = None
    newName: str | None = None
    newId: int | None = None
    lockTimeout: str | None = None
    noLock: bool | None = None


# @router.get("/model/entity")
# async def model_entity_get(
#     selector: str = Query(...),
#     by: str = Query("auto"),
#     solutionPath: str | None = Query(None),
# ) -> ModelDocumentResponse:
#     """Read a model entity by selector."""
#     entity = resolve_model_entity(selector, solution_path=solutionPath, by=by)
#     content = model_model.ModelEntity.model_validate(
#         workspace_io.read_workspace_json(entity.rel_path, solutionPath)
#     )
#     return ModelDocumentResponse(
#         entity=entity.rel_path, content=_dump_sparse_json(content)
#     )


@router.post("/model/entity/create")
async def model_entity_create(body: ModelEntityCreateBody) -> MessageWithPathResponse:
    """Create a model entity file."""
    abs_path = workspace_service.create_model_entity(
        rel_path=body.relPath,
        name=body.name,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="created", absPath=abs_path)


@router.post("/model/entity/validate")
async def model_entity_validate(
    body: ModelEntitySelectorBody,
) -> ValidationStatusResponse:
    """Validate that a model entity matches the schema."""
    entity = resolve_model_entity(body.selector, solution_path=body.solutionPath, by=body.by)
    try:
        model_model.ModelEntity.model_validate(
            workspace_io.read_workspace_json(entity.rel_path, body.solutionPath)
        )
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Model entity validation failed.",
            details={"relPath": entity.rel_path, "errors": e.errors()},
        )
    return ValidationStatusResponse(status="ok", relPath=entity.rel_path)


@router.post("/model/entity/set")
async def model_entity_set(body: ModelEntitySetBody) -> MessageWithPathResponse:
    """Set a JSON pointer value in a model entity."""
    entity = resolve_model_entity(body.selector, solution_path=body.solutionPath, by=body.by)
    current = workspace_io.read_workspace_json(entity.rel_path, body.solutionPath)
    next_doc = set_by_pointer(current, body.pointer, body.value, create_missing=body.createMissing)
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=next_doc,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.post("/model/entity/patch")
async def model_entity_patch(body: ModelEntityPatchBody) -> MessageWithPathResponse:
    """Apply a JSON merge patch to a model entity."""
    entity = resolve_model_entity(body.selector, solution_path=body.solutionPath, by=body.by)
    current = workspace_io.read_workspace_json(entity.rel_path, body.solutionPath)
    next_doc = merge_patch(current, body.patch)
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=next_doc,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.post("/model/entity/duplicate")
async def model_entity_duplicate(body: DuplicateEntityBody) -> MoveEntityResponse:
    """Duplicate a model entity file."""
    result = workspace_service.duplicate_model_entity(
        from_rel_path=body.fromRelPath,
        to_rel_path=body.toRelPath,
        solution_path=body.solutionPath,
        new_name=body.newName,
        new_id=body.newId,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MoveEntityResponse(
        message="duplicated",
        **{"from": result.fromAbsPath, "to": result.toAbsPath},
    )


@router.get(
    "/model/entities",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def model_entities(path: str | None = Query(None)) -> ModelEntitiesResponse:
    """List model entities for the active solution."""
    entities = [
        ModelEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in workspace_service.list_model_entities(path)
    ]
    return ModelEntitiesResponse(count=len(entities), entities=entities)


@router.post("/model/entities")
async def model_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a model entity file."""
    abs_path = workspace_service.save_model_entity(
        rel_path=body.relPath,
        content=body.content,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/model/entities")
async def model_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a model entity file."""
    abs_path = workspace_service.delete_model_entity(
        rel_path=body.relPath,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.post("/model/entities/move")
async def model_entities_move(body: MoveEntityBody) -> MoveEntityResponse:
    """Move a model entity file."""
    result = workspace_service.move_model_entity(
        from_rel_path=body.fromRelPath,
        to_rel_path=body.toRelPath,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MoveEntityResponse(
        message="moved",
        **{"from": result.fromAbsPath, "to": result.toAbsPath},
    )


@router.post(
    "/model/folder/rename",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def model_folder_rename(body: RenameFolderBody) -> RenameFolderResponse:
    """Rename a model folder and regenerate index."""
    result = workspace_service.rename_model_folder(
        from_folder_rel_path=body.fromFolderRelPath,
        to_folder_rel_path=body.toFolderRelPath,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    entities = [
        ModelEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in result.entities
    ]
    return RenameFolderResponse(
        message="renamed",
        entities=entities,
        **{"from": result.fromAbsPath, "to": result.toAbsPath},
    )


@router.get("/model/folder-metadata")
async def model_folder_metadata_get(
    relPath: str = Query(...),
    solutionPath: str | None = Query(None),
) -> JsonDocumentResponse:
    """Read folder metadata from a `.properties.json` file."""
    content = workspace_service.read_folder_metadata(rel_path=relPath, solution_path=solutionPath)
    return JsonDocumentResponse(relPath=relPath, content=_dump_sparse_json(content))


@router.post("/model/folder-metadata")
async def model_folder_metadata_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save folder metadata in a `.properties.json` file."""
    abs_path = workspace_service.save_folder_metadata(
        rel_path=body.relPath,
        content=body.content,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/model/folder-metadata")
async def model_folder_metadata_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete folder metadata `.properties.json` file."""
    abs_path = workspace_service.delete_folder_metadata(
        rel_path=body.relPath,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.post("/refactor/properties")
async def refactor_properties_route(
    body: RefactorPropertiesBody,
) -> RefactorPropertiesResponse:
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
    index = workspace_service.regenerate_index(
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return IndexRegenerateResponse(message="index regenerated", index=index)


@router.get("/index/show")
async def index_show(path: str | None = Query(None)) -> IndexShowResponse:
    """Return current solution index."""
    return IndexShowResponse(index=read_index(path))


@router.get("/index/validate")
async def index_validate_route(path: str | None = Query(None)) -> IndexValidateResponse:
    """Return validation report for current index."""
    return IndexValidateResponse(report=validate_index(path))


@router.post("/generate", response_model=generate.GenerateResult)
async def generator_run(body: GenerateBody) -> generate.GenerateResult:
    """Execute generator synchronously."""

    # The API server is long-lived; decorators in target modules would otherwise
    # re-register payloads on subsequent runs and fail with "already registered".
    generate.payload_functions.clear()

    model = factory.get_model()  # currently loaded model

    result = generate.generate_output(
        model,
        target=body.target or opts.default_target,
        clean_output=body.cleanOutput or False,
        payloads=body.payloads or [],
        generate_all=False,
    )

    return result


@router.get("/entities/{locator:path}", response_model=None)
async def get_entities(locator: str = "/") -> list[model.EntityWrapperVariant]:
    """
    Returns a list of entities based on the given locator. Returns an empty list if none are found.
    """
    return factory.get_model().get_entities(locator)


@router.patch("/entities/{locator:path}")
async def patch_entity(locator: str, patch: dict[str, Any]) -> model.EntityWrapperVariant:
    wrapper = factory.get_model().get_entity_by_locator(locator)
    wrapper.update(**patch)
    return wrapper


@router.delete("/entities/{locator:path}")
async def delete_entity(locator: str) -> dict[str, Any]:
    deleted_locators = factory.get_model().delete_entities(locator)

    return {
        "deleted_entities": len(deleted_locators),
        "deleted_locators": deleted_locators,
    }


@router.put("/entities/{locator:path}")
async def create_entity(
    locator: str, body: dict[str, Any]
) -> model.EntityWrapper[b.BaseEntityType]:
    entity = factory.get_model().add_entity(locator, body)
    return entity


@router.post("/entities/move")
async def move_entities(body: dict[str, str]) -> list[model.EntityWrapperVariant]:
    # note sure how to validate in fast api that these to parameters are set in the body
    _from = body["from"]
    _to = body["to"]

    return factory.get_model().move_entities(_from, _to)


@router.post("/model/save")
async def model_save(
    body: dict[str, Any] = Body(default_factory=lambda: {"locator": None}),
) -> None:
    factory.get_model().save(body["locator"])


@router.get("/model/reload")
async def model_reload(force: bool = Query(False)) -> dict[str, Any]:
    pending_changes, pending_deletions = factory.get_model().get_unsaved_entities()
    if (len(pending_changes) > 0 or len(pending_deletions) > 0) and not force:
        raise HTTPException(status_code=409, detail="")

    factory._model = await factory.load_model(config.solution_path)

    return {"reloadedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z")}


@router.get("/model/unsaved")
async def get_unsaved() -> dict[str, list[str]]:
    changed, deleted = factory.get_model().get_unsaved_entities()
    return {
        "changed": list(map(str, changed)),
        "deleted": list(map(str, deleted)),
    }


@router.get(
    "/base/entities",
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def base_entities(path: str | None = Query(None)) -> BaseEntitiesResponse:
    """List base entities for the active solution."""
    entities = [
        BaseEntityResponse(
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in workspace_service.list_base_entities(path)
    ]
    return BaseEntitiesResponse(count=len(entities), entities=entities)


@router.get("/base/entity")
async def base_entity_get(
    relPath: str = Query(...),
    solutionPath: str | None = Query(None),
) -> JsonDocumentResponse:
    """Read a base entity JSON document."""

    logger.info("input: %s", relPath)

    content = workspace_io.read_base_entity(relPath, solutionPath)
    return JsonDocumentResponse(relPath=relPath, content=_dump_sparse_json(content))


@router.post("/base/entities")
async def base_entities_save(body: SaveEntityBody) -> MessageWithPathResponse:
    """Save a base entity file."""
    abs_path = workspace_service.save_base_entity(
        rel_path=body.relPath,
        content=body.content,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.delete("/base/entities")
async def base_entities_delete(body: DeleteEntityBody) -> MessageWithPathResponse:
    """Delete a base entity file."""
    abs_path = workspace_service.delete_base_entity(
        rel_path=body.relPath,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.post("/base/entity/set")
async def base_entity_set(body: SetByPointerBody) -> MessageWithPathResponse:
    """Set a JSON pointer value in a base entity."""
    current = workspace_io.read_workspace_json(body.relPath, body.solutionPath)
    next_doc = set_by_pointer(
        current,
        body.pointer,
        body.value,
        create_missing=body.createMissing,
    )
    abs_path = workspace_service.save_base_entity(
        rel_path=body.relPath,
        content=next_doc,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.post("/base/entity/patch")
async def base_entity_patch(body: PatchEntityBody) -> MessageWithPathResponse:
    """Apply JSON merge-patch to a base entity."""
    current = workspace_io.read_workspace_json(body.relPath, body.solutionPath)
    next_doc = merge_patch(current, body.patch)
    abs_path = workspace_service.save_base_entity(
        rel_path=body.relPath,
        content=next_doc,
        solution_path=body.solutionPath,
        no_lock=bool(body.noLock),
        lock_timeout=lock_timeout_seconds(body.model_dump()),
    )
    return MessageWithPathResponse(message="saved", absPath=abs_path)


@router.get("/fs/list")
async def fs_list(path: str | None = Query(None)) -> EntriesResponse:
    """List directory entries inside the active workspace."""
    entries = [
        DirectoryEntryResponse.model_validate(entry.model_dump())
        for entry in workspace_io.list_directory(path)
    ]
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
async def model_function_source_save(
    body: FunctionSourceSaveBody,
) -> MessageWithPathResponse:
    """Save model function source content."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=parse_duration_seconds("10s"),
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
async def model_function_source_rename(
    body: FunctionSourceRenameBody,
) -> FunctionSourceRenameResponse:
    """Rename model function source key."""
    resolved, _sol = workspace_io.read_solution(body.solutionPath)
    with SolutionLock(
        resolved.root_dir / ".datam8.lock",
        timeout_seconds=parse_duration_seconds("10s"),
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
async def script_list(
    path: str = Query(...), solutionPath: str | None = Query(None)
) -> ScriptListResponse:
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
        timeout_seconds=parse_duration_seconds("10s"),
    ):
        abs_path = workspace_io.delete_function_source(path, source, solutionPath, None)
    return MessageWithPathResponse(message="deleted", absPath=abs_path)


@router.get("/search/entities")
async def search_entities_route(
    q: str = Query(...), path: str | None = Query(None)
) -> SearchEntitiesResponse:
    """Search entities by metadata fields."""
    result = search_core.search_entities(solution_path=path, query=q)
    return SearchEntitiesResponse(count=result["count"], entities=result["entities"])


@router.get("/search/text")
async def search_text_route(
    q: str = Query(...), path: str | None = Query(None)
) -> SearchTextResponse:
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
            timeout_seconds=parse_duration_seconds("10s"),
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
            timeout_seconds=parse_duration_seconds("10s"),
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
            timeout_seconds=parse_duration_seconds("10s"),
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
