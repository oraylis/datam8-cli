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
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

refactor_router = APIRouter(prefix="/refactor")


class RefactorPrpertyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    updated_files: Annotated[int, Field(alias="updatedFiles")]


@refactor_router.post("/property")
async def refactor_property() -> RefactorPrpertyResponse:
    raise HTTPException(status_code=501)


class RefactorEntityIdBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_id: Annotated[int, Field(alias="fromId")]
    to_id: Annotated[int, Field(alias="toId")]


@refactor_router.post("/model-entity-id")
async def refactor_model_entity_id(body: RefactorEntityIdBody) -> None:
    raise HTTPException(status_code=501)


@refactor_router.post("/folder-entity-id")
async def refactor_folder_entity_id(body: RefactorEntityIdBody) -> None:
    raise HTTPException(status_code=501)
