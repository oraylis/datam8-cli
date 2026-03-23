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
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datam8 import factory
from datam8.model import Locator
from datam8_model.model import ExternalModelSource

sources_router = APIRouter(prefix="/sources")


@sources_router.get("/{data_source}/validate-connection")
async def validate_connection(data_source: str) -> None:
    "Validate datasource connection properties"
    ds = factory.get_plugin_for_data_source(data_source)
    error = ds.validate_connection()

    if isinstance(error, Exception):
        raise HTTPException(status_code=500, detail=str(error))


@sources_router.get("/{data_source}/list-tables")
async def list_tables(data_source: str) -> list[str]:
    "List available source tables for a datasource connector"
    plugin = factory.get_plugin_for_data_source(data_source)
    return plugin.list_tables()


@sources_router.get("/{data_source}/test")
async def test_connection(data_source: str) -> None:
    plugin = factory.get_plugin_for_data_source(data_source)
    error = plugin.test_connection()

    if isinstance(error, Exception):
        raise HTTPException(status_code=500, detail=str(error))


class TableMetadataBody(BaseModel):
    table: str
    schema: str | None = None


@sources_router.post("/{data_source}/table-metadata")
async def get_table_metadata(data_source: str, body: TableMetadataBody) -> dict[str, Any]:
    plugin = factory.get_plugin_for_data_source(data_source)
    return plugin.get_table_metadata(body.table, body.schema)


class PreviewBody(TableMetadataBody):
    limit: int = 10


@sources_router.post("/{data_source}/preview")
async def preview(data_source: str, body: PreviewBody) -> list[Any]:
    plugin = factory.get_plugin_for_data_source(data_source)
    return plugin.preview_data(body.table, body.schema, limit=body.limit)


# NOTE: not sure what this is supposed to be?
@sources_router.post("/{data_source}/virtual-table-metadata")
async def get_virtual_table_metadata(data_source: str, body: TableMetadataBody) -> dict[str, Any]:
    raise HTTPException(status_code=404, detail="NotImplemented")


@sources_router.get("/{data_source}/usages")
async def get_usages(data_source: str) -> list[Locator]:
    model_ = factory.get_model()
    ds = model_.get_data_source(data_source)
    entities = [
        wrapper.locator
        for wrapper in factory.get_model().modelEntities.values()
        if ds.entity.name
        in [s.dataSource for s in wrapper.entity.sources if isinstance(s, ExternalModelSource)]
    ]
    return entities
