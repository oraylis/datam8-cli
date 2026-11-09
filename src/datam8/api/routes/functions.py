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
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from datam8 import factory, functions
from datam8.model import EntityWrapper
from datam8.operations import ModelSession, Operation
from datam8_model.model import ModelEntity

from .responses import (
    MultiItemResponse,
    Response204NoContent,
    SingleItemResponse,
)

functions_router = APIRouter(prefix="/functions", tags=["functions"])

# ==============================================================================
# GET MULTIPLE FUNCTIONS
# ==============================================================================


@functions_router.get("")
async def get_all_functions() -> MultiItemResponse[functions.Function]:
    funcs: list[functions.Function] = []
    repo = factory.get_model().modelEntities

    for wrapper in repo.values():
        funcs.extend(functions.get_functions(wrapper))

    return MultiItemResponse.from_list(funcs)


def _get_wrapper_by_id(id: int) -> EntityWrapper[ModelEntity]:
    repo = factory.get_model().modelEntities
    return repo.get_by_id(id)


@functions_router.get("/{modelEntityId:int}")
async def get_functions_for_model_entity(
    modelEntityId: int,
) -> MultiItemResponse[functions.Function]:
    wrapper = _get_wrapper_by_id(modelEntityId)
    return MultiItemResponse.from_list(functions.get_functions(wrapper))


# ==============================================================================
# GET SINGLE FUNCTION BY STEP OR NAME
# ==============================================================================


def _get_wrapper_function(
    id: int, step_no_or_name: int | str
) -> tuple[EntityWrapper[ModelEntity], functions.Function]:
    wrapper = _get_wrapper_by_id(id)
    return wrapper, functions.get_function(wrapper, step_no_or_name)


@functions_router.get("/{modelEntityId:int}/{stepNo:int}")
async def get_function_for_entity_with_step_no(
    modelEntityId: int, stepNo: int
) -> SingleItemResponse[functions.Function]:
    _, func = _get_wrapper_function(modelEntityId, stepNo)
    return SingleItemResponse(item=func)


@functions_router.get("/{modelEntityId:int}/{name:str}")
async def get_function_for_entity_with_name(
    modelEntityId: int, name: str
) -> SingleItemResponse[functions.Function]:
    _, func = _get_wrapper_function(modelEntityId, name)
    return SingleItemResponse(item=func)


# ==============================================================================
# UPDATING FUNCTION
# ==============================================================================


class UpdateFunctionBody(BaseModel):
    source_code: Annotated[str, Field(alias="sourceCode")]


class CreateFunctionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    step_no: Annotated[int, Field(alias="stepNo", ge=1)]
    name: str
    source: str
    source_code: Annotated[str, Field(alias="sourceCode")]


@functions_router.post("/{modelEntityId:int}")
async def create_function(modelEntityId: int, body: CreateFunctionBody) -> Response:
    wrapper = _get_wrapper_by_id(modelEntityId)
    operation = Operation(
        op="functions.create",
        locator=str(wrapper.locator),
        data={
            "stepNo": body.step_no,
            "name": body.name,
            "kind": "function",
            "function": {"source": body.source},
        },
        source_code=body.source_code,
    )
    ModelSession(model=factory.get_model()).execute(operation)
    return Response204NoContent()


@functions_router.delete("/{modelEntityId:int}/{stepNo:int}")
async def delete_function_with_step_no(modelEntityId: int, stepNo: int) -> Response:
    wrapper = _get_wrapper_by_id(modelEntityId)
    ModelSession(model=factory.get_model()).execute(
        Operation(op="functions.delete", locator=str(wrapper.locator), step_no=stepNo)
    )
    return Response204NoContent()


@functions_router.delete("/{modelEntityId:int}/{name:str}")
async def delete_function_with_name(modelEntityId: int, name: str) -> Response:
    wrapper = _get_wrapper_by_id(modelEntityId)
    ModelSession(model=factory.get_model()).execute(
        Operation(op="functions.delete", locator=str(wrapper.locator), name=name)
    )
    return Response204NoContent()


def _update_function(id: int, step_no_or_name: str | int, source_code: str) -> None:
    wrapper = _get_wrapper_by_id(id)
    functions.update_function(wrapper, step_no_or_name, source_code)


@functions_router.post("/{modelEntityId:int}/{stepNo:int}")
async def update_function_with_step_no(
    body: UpdateFunctionBody, modelEntityId: int, stepNo: int
) -> Response:
    _update_function(modelEntityId, stepNo, body.source_code)
    return Response204NoContent()


@functions_router.post("/{modelEntityId:int}/{name:str}")
async def update_function_with_name(
    body: UpdateFunctionBody, modelEntityId: int, name: str
) -> Response:
    _update_function(modelEntityId, name, body.source_code)
    return Response204NoContent()


# ==============================================================================
# MOVING FUNCTION
# ==============================================================================


class MoveFunctionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    new_path: Annotated[
        Path,
        Field(
            alias="newPath",
            description="Path where to move the function. Relative to the entities source file path.",
        ),
    ]
    force: bool = False


def _move_function(
    modelEntityId: int, step_no_or_name: int | str, new_path: Path, force: bool
) -> None:
    wrapper, func = _get_wrapper_function(modelEntityId, step_no_or_name)
    functions.move_function(
        wrapper, func.transformation, wrapper.source_file.parent / new_path, force=force
    )


@functions_router.post("/{modelEntityId:int}/{stepNo:int}/move")
async def move_function_with_step_no(body: MoveFunctionBody, modelEntityId: int, stepNo: int):
    _move_function(modelEntityId, stepNo, body.new_path, body.force)
    return Response204NoContent()


@functions_router.post("/{modelEntityId:int}/{name:str}/move")
async def move_function_with_name(body: MoveFunctionBody, modelEntityId: int, name: str):
    _move_function(modelEntityId, name, body.new_path, body.force)
    return Response204NoContent()
