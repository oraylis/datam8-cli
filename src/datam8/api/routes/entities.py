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
from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from datam8 import factory, model
from datam8_model import base as b

from .responses import MultiItemResponse, SingleItemResponse

entities_router = APIRouter(prefix="/entities", tags=["entities"])


@entities_router.get("")
async def get_all_entities() -> MultiItemResponse[model.EntityWrapperVariant]:
    entities = list(factory.get_model().get_entity_iterator())
    return MultiItemResponse.from_list(entities)


@entities_router.get("/{locator:path}")
async def get_entities(locator: str = "/") -> MultiItemResponse[model.EntityWrapperVariant]:
    """
    Returns a list of entities based on the given locator. Returns an empty list if none are found.
    """
    entities = factory.get_model().get_entities(locator)
    return MultiItemResponse.from_list(entities)


@entities_router.patch("/{locator:path}")
async def patch_entity(
    patch: dict[str, Any], locator: str
) -> SingleItemResponse[model.EntityWrapperVariant]:
    wrapper = factory.get_model().get_entity_by_locator(locator)
    wrapper.update(**patch)
    return SingleItemResponse(item=wrapper)


@entities_router.delete("/{locator:path}")
async def delete_entity(locator: str) -> MultiItemResponse[model.Locator]:
    deleted_locators = factory.get_model().delete_entities(locator)
    return MultiItemResponse.from_list(deleted_locators)


class CloneEntityBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    locator: str
    new_locator: Annotated[str, Field(alias="newLocator")]


@entities_router.put("/clone")
async def clone_entity(
    body: CloneEntityBody,
) -> MultiItemResponse[model.EntityWrapper[b.BaseEntityType]]:
    entity = factory.get_model().clone_entity(body.locator, body.new_locator)
    return MultiItemResponse.from_list([entity])


@entities_router.put("/{locator:path}")
async def create_entity(
    body: dict[str, Any], locator: str
) -> SingleItemResponse[model.EntityWrapper[b.BaseEntityType]]:
    entity = factory.get_model().add_entity(locator, body)
    return SingleItemResponse(item=entity)


class RenameBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: Annotated[str, Field(alias="from")]
    to: str


@entities_router.post("/rename")
async def rename_entity(
    body: RenameBody,
) -> SingleItemResponse[model.EntityWrapperVariant]:
    entity = factory.get_model().rename_entity(body.from_, body.to)
    return SingleItemResponse(item=entity)


class MoveBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: Annotated[str, Field(alias="from")]
    to: Annotated[str, Field(alias="to")]


@entities_router.post("/move")
async def move_entities(body: MoveBody) -> MultiItemResponse[model.EntityWrapperVariant]:
    moved_entities = factory.get_model().move_entities(body.from_, body.to)
    return MultiItemResponse.from_list(moved_entities)


@entities_router.post("/move-single")
async def move_entity(body: MoveBody) -> SingleItemResponse[model.EntityWrapperVariant]:
    from_ = model.Locator.from_path(body.from_)
    to = model.Locator.from_path(body.to)
    moved_entity = factory.get_model().move_entity(from_, to)
    return SingleItemResponse(item=moved_entity)
