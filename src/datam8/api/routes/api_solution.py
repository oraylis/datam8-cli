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
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from datam8.core import (
    migration_v1_to_v2 as migration_v1_to_v2_core,
)
from datam8.core import solution_files, workspace_io

from .response_models import (
    BaseEntityResponse,
    ConfigResponse,
    MigrationResponse,
    ModelEntityResponse,
    ResolvedPathsResponse,
    SolutionFullResponse,
    SolutionPathResponse,
    SolutionResponse,
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
    return VersionResponse(version=solution_files.detect_solution_version(path))


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


@router.get("/solution/full")
async def solution_full(path: str | None = Query(None)) -> SolutionFullResponse:
    """Read and return the full solution with base/model entities."""
    _resolved, sol = workspace_io.read_solution(path)
    base_entities = [
        BaseEntityResponse.model_validate(entity.model_dump())
        for entity in workspace_io.list_base_entities(path)
    ]
    model_entities = [
        ModelEntityResponse.model_validate(entity.model_dump())
        for entity in workspace_io.list_model_entities(path)
    ]
    return SolutionFullResponse(
        solution=sol,
        baseEntities=base_entities,
        modelEntities=model_entities,
    )


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
