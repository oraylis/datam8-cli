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
import json
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from datam8 import factory, source
from datam8.model import EntityWrapper, Locator
from datam8_model.data_source import SourceField, SourceObject
from datam8_model.model import ExternalModelSource, ModelEntity
from datam8_model.plugin import Capability

from .responses import MultiItemResponse

sources_router = APIRouter(prefix="/sources", tags=["sources"])


@sources_router.get("/{data_source}/test")
async def test_connection(data_source: str) -> None:
    plugin = factory.get_plugin_for_data_source(data_source)
    error = plugin.test_connection()

    if isinstance(error, Exception):
        raise HTTPException(status_code=500, detail=str(error))


@sources_router.get("/{data_source}/locations")
async def list_locations(
    data_source: str, source_location: str | None = None
) -> MultiItemResponse[dict[str, Any]]:
    "List available source tables if a source does not support schemas"
    plugin = factory.get_plugin_for_data_source(data_source)
    locations = plugin.list_source(source_location).to_dicts()
    return MultiItemResponse.from_list(locations)


@sources_router.get("/{data_source}/locations/metadata")
async def get_table_metadata(
    data_source: str, source_location: str
) -> MultiItemResponse[SourceField]:
    plugin = factory.get_plugin_for_data_source(data_source)
    metadata = plugin.get_table_metadata(source_location)
    source_fields = list(metadata.iter_source_fields())
    return MultiItemResponse.from_list(source_fields)


@sources_router.get("/{data_source}/locations/preview")
async def preview(
    data_source: str, source_location: str, limit: int = 10
) -> MultiItemResponse[dict[str, Any]]:
    plugin = factory.get_plugin_for_data_source(data_source)
    if not plugin.is_capable_of(Capability.PREVIEW_DATA):
        raise HTTPException(status_code=400, detail="Plugin does not support data preview")
    preview = plugin.preview_data(source_location, limit=limit)

    for df in preview.collect_batches(chunk_size=limit):
        rows = df.to_dicts()
        return MultiItemResponse.from_list(rows)

    raise HTTPException(status_code=404, detail="No data to preview")


class ImportBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    locator: str
    source_location: Annotated[str, Field(alias="sourceLocation")]


@sources_router.put("/{data_source}/import")
async def import_(data_source: str, body: ImportBody) -> EntityWrapper[ModelEntity]:
    model_ = factory.get_model()
    new_wrapper = source.import_from_source(
        data_source, body.source_location, body.locator, model=model_
    )
    model_.save(body.locator)
    return new_wrapper


def _source_object_from_row(
    row: dict[str, Any],
    *,
    fallback_schema: str | None = None,
) -> SourceObject:
    name = row.get("object", row.get("name"))
    if name is None:
        raise HTTPException(status_code=502, detail="Plugin returned a source row without a name")

    return SourceObject.from_dict(
        {
            "schema": str(row.get("schema") or fallback_schema)
            if row.get("schema") or fallback_schema
            else None,
            "name": str(name),
            "type": str(row.get("type", "OBJECT")),
            "description": row.get("description"),
            "properties": row.get("properties"),
            "sourceOverride": row.get("sourceOverride"),
        }
    )


def _compatibility_source_location(schema: str | None, table: str) -> str:
    return f"{schema}.{table}" if schema else table


@sources_router.get("/{data_source}/schemas")
async def list_schemas(data_source: str) -> MultiItemResponse[str]:
    plugin = factory.get_plugin_for_data_source(data_source)
    schemas = []
    for row in plugin.list_source(None).to_dicts():
        if row.get("schema") is not None:
            schema = str(row["schema"])
            if schema not in schemas:
                schemas.append(schema)
    return MultiItemResponse.from_list(schemas)


@sources_router.get("/{data_source}/schemas/{schema}/tables")
async def list_tables_for_schema(
    data_source: str,
    schema: str,
) -> MultiItemResponse[SourceObject]:
    plugin = factory.get_plugin_for_data_source(data_source)
    tables = [
        _source_object_from_row(row, fallback_schema=schema)
        for row in plugin.list_source(schema).to_dicts()
    ]
    return MultiItemResponse.from_list(tables)


@sources_router.get("/{data_source}/schemas/{schema}/tables/{table}")
async def get_table_metadata_for_schema(
    data_source: str,
    schema: str,
    table: str,
) -> MultiItemResponse[SourceField]:
    return await get_table_metadata(
        data_source,
        _compatibility_source_location(schema, table),
    )


@sources_router.get("/{data_source}/schemas/{schema}/tables/{table}/preview")
async def preview_for_schema(
    data_source: str,
    schema: str,
    table: str,
    limit: int = 10,
) -> MultiItemResponse[dict[str, Any]]:
    return await preview(
        data_source,
        _compatibility_source_location(schema, table),
        limit,
    )


class CompatibilityImportBody(BaseModel):
    locator: str


@sources_router.put("/{data_source}/schemas/{schema}/tables/{table}/import")
async def import_for_schema(
    data_source: str,
    schema: str,
    table: str,
    body: CompatibilityImportBody,
) -> EntityWrapper[ModelEntity]:
    return await import_(
        data_source,
        ImportBody(
            locator=body.locator,
            source_location=_compatibility_source_location(schema, table),
        ),
    )


@sources_router.get("/{data_source}/tables")
async def list_tables_without_schema(
    data_source: str,
) -> MultiItemResponse[SourceObject]:
    plugin = factory.get_plugin_for_data_source(data_source)
    tables = [_source_object_from_row(row) for row in plugin.list_source(None).to_dicts()]
    return MultiItemResponse.from_list(tables)


@sources_router.get("/{data_source}/tables/{table}")
async def get_table_metadata_without_schema(
    data_source: str,
    table: str,
) -> MultiItemResponse[SourceField]:
    return await get_table_metadata(data_source, table)


@sources_router.get("/{data_source}/tables/{table}/preview")
async def preview_without_schema(
    data_source: str,
    table: str,
    limit: int = 10,
) -> MultiItemResponse[dict[str, Any]]:
    return await preview(data_source, table, limit)


@sources_router.put("/{data_source}/tables/{table}/import")
async def import_without_schema(
    data_source: str,
    table: str,
    body: CompatibilityImportBody,
) -> EntityWrapper[ModelEntity]:
    return await import_(
        data_source,
        ImportBody(locator=body.locator, source_location=table),
    )


class CompareResponse(BaseModel):
    wrapper: EntityWrapper[ModelEntity]
    diff: dict[str, Any]
    has_changes: bool


@sources_router.get("/compare")
async def compare_with_source(locator: str) -> CompareResponse:
    model_ = factory.get_model()
    wrapper, diff = source.compare_entity_with_source(locator, model=model_)
    return CompareResponse(
        # convert custom objects from DeepDiff into plain dicts/objects
        wrapper=wrapper,
        diff=json.loads(diff.to_json()),
        has_changes=wrapper._changed,
    )


#
# additional routes
#


# TODO: not sure what this is supposed to be?
# @sources_router.post("/{data_source}/virtual-table-metadata")
# async def get_virtual_table_metadata(data_source: str, body: TableMetadataBody) -> dict[str, Any]:
#     raise HTTPException(status_code=404, detail="NotImplemented")


@sources_router.get("/{data_source}/usages")
async def get_usages(data_source: str) -> MultiItemResponse[Locator]:
    model_ = factory.get_model()
    ds = model_.dataSources.get(data_source)
    entities = [
        wrapper.locator
        for wrapper in factory.get_model().modelEntities.values()
        if ds.entity.name
        in [s.dataSource for s in wrapper.entity.sources if isinstance(s, ExternalModelSource)]
    ]
    return MultiItemResponse.from_list(entities)
