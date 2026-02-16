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

import os
from functools import partial
from typing import Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from pydantic_core import ValidationError

from datam8 import factory, model_exceptions, parser_exceptions
from datam8.core import (
    migration_v1_to_v2 as migration_v1_to_v2_core,
)
from datam8.core import workspace_io, workspace_service
from datam8.core.errors import Datam8ValidationError
from datam8.core.solution_index import detect_solution_version

from .response_models import (
    BaseEntityResponse,
    ConfigResponse,
    FolderEntityResponse,
    MigrationResponse,
    ModelEntityResponse,
    ResolvedPathsResponse,
    SolutionFullResponse,
    SolutionInfoResponse,
    SolutionPathResponse,
    SolutionResponse,
    SolutionValidateResponse,
    VersionResponse,
)

router = APIRouter()


class MigrateV1ToV2Body(BaseModel):
    """Request body for migrating a v1 solution to v2."""

    sourceSolutionPath: str
    targetDir: str
    options: dict[str, Any] | None = None


class NewProjectBody(BaseModel):
    """Request body for creating a new minimal solution project."""

    solutionName: str
    projectRoot: str
    basePath: str | None = None
    modelPath: str | None = None
    target: str


@router.get("/config")
async def config() -> ConfigResponse:
    """Return runtime configuration metadata consumed by the frontend."""
    return ConfigResponse(mode=os.environ.get("DATAM8_MODE") or "server")


@router.get("/solution/inspect")
async def solution_inspect(path: str = Query(...)) -> VersionResponse:
    """Detect and return the solution format version."""
    return VersionResponse(version=detect_solution_version(path))


@router.post("/migration/v1-to-v2")
async def migration_v1_to_v2_route(body: MigrateV1ToV2Body) -> MigrationResponse:
    """Migrate a v1 solution into v2 structure."""
    args: dict[str, Any] = {
        "sourceSolutionPath": body.sourceSolutionPath,
        "targetDir": body.targetDir,
    }
    if body.options is not None:
        args["options"] = body.options
    return MigrationResponse.model_validate(
        migration_v1_to_v2_core.migrate_solution_v1_to_v2(args)
    )


@router.get("/solution")
async def solution(path: str | None = Query(None)) -> SolutionResponse:
    """Read and return the parsed solution with resolved paths."""
    _resolved, sol = workspace_io.read_solution(path)
    return SolutionResponse(
        solution=sol,
        resolvedPaths=ResolvedPathsResponse(base=str(sol.basePath), model=str(sol.modelPath)),
    )


@router.get("/solution/info")
async def solution_info(path: str | None = Query(None)) -> SolutionInfoResponse:
    """Return resolved solution metadata including solution path."""
    resolved, sol = workspace_io.read_solution(path)
    return SolutionInfoResponse(
        solutionPath=str(resolved.solution_file),
        solution=sol,
        resolvedPaths=ResolvedPathsResponse(base=str(sol.basePath), model=str(sol.modelPath)),
    )


@router.get("/solution/full")
async def solution_full(path: str | None = Query(None)) -> SolutionFullResponse:
    """Read and return the full solution with base/model entities."""
    snapshot = workspace_service.get_solution_full_snapshot(path)
    base_entities = [
        BaseEntityResponse(
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in snapshot.baseEntities
    ]
    model_entities = [
        ModelEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            content=entity.content,
        )
        for entity in snapshot.modelEntities
    ]
    folder_entities = [
        FolderEntityResponse(
            locator=entity.locator,
            name=entity.name,
            absPath=entity.absPath,
            relPath=entity.relPath,
            folderPath=entity.folderPath,
            content=entity.content,
        )
        for entity in snapshot.folderEntities
    ]
    return SolutionFullResponse(
        solution=snapshot.solution,
        baseEntities=base_entities,
        modelEntities=model_entities,
        folderEntities=folder_entities,
    )


@router.post("/solution/validate")
async def solution_validate(path: str | None = Query(None)) -> SolutionValidateResponse:
    """Validate that a solution can be resolved and parsed."""
    resolved, _sol = workspace_io.read_solution(path)
    return SolutionValidateResponse(status="ok", solutionPath=str(resolved.solution_file))


@router.post("/validate")
async def validate(path: str | None = Query(None), logLevel: str | None = Query(None)) -> SolutionValidateResponse:
    """Validate full model parsing/resolution (CLI `datam8 validate` parity)."""
    candidate = path or os.environ.get("DATAM8_SOLUTION_PATH")
    if not candidate:
        raise Datam8ValidationError(
            message="No solution specified. Use path query parameter or DATAM8_SOLUTION_PATH.",
            details=None,
        )

    try:
        resolved_solution = await run_in_threadpool(
            partial(
                factory.validate_solution_model,
                solution_path=candidate,
                log_level=logLevel,
            )
        )
    except (
        RecursionError,
        ValidationError,
        parser_exceptions.ModelParseException,
        parser_exceptions.NotSupportedModelVersion,
        model_exceptions.EntityNotFoundError,
        model_exceptions.PropertiesNotResolvedError,
    ) as err:
        raise Datam8ValidationError(
            message="Solution model validation failed.",
            details={"error": str(err)},
        )

    return SolutionValidateResponse(status="ok", solutionPath=str(resolved_solution))


@router.post("/solution/new-project")
async def solution_new_project(body: NewProjectBody) -> SolutionPathResponse:
    """Create a new minimal project and return solution path."""
    solution_path = workspace_io.create_new_project(
        solution_name=body.solutionName,
        project_root=body.projectRoot,
        base_path=body.basePath,
        model_path=body.modelPath,
        target=body.target,
    )
    return SolutionPathResponse(solutionPath=solution_path)
