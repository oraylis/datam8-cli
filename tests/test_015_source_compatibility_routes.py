# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import asyncio
from types import SimpleNamespace

import polars as pl

from datam8 import factory
from datam8.api.routes import sources
from datam8.plugins.base import TableMetadata
from datam8_model.data_source import SourceObject
from datam8_model.plugin import Capability


class CompatibilityPluginStub:
    def list_source(self, source_location: str | None):
        if source_location is None:
            return pl.DataFrame([{"schema": "dbo"}, {"schema": "sales"}])
        return pl.DataFrame(
            [
                {
                    "schema": source_location,
                    "object": "Customer",
                    "type": "TABLE",
                    "description": "Customer master",
                }
            ]
        )

    def get_table_metadata(self, source_location: str) -> TableMetadata:
        schema, table = source_location.split(".", maxsplit=1)
        return TableMetadata(
            pl.DataFrame(
                [
                    {
                        "name": "CustomerId",
                        "ordinal": 1,
                        "dataType": "int",
                        "isNullable": False,
                    }
                ]
            ),
            SourceObject(schema=schema, name=table, type="TABLE"),
        )

    def preview_data(self, source_location: str, *, limit: int):
        return pl.DataFrame(
            [{"sourceLocation": source_location, "limit": limit}]
        ).lazy()

    def is_capable_of(self, capability: Capability) -> bool:
        return capability == Capability.PREVIEW_DATA


def test_schema_adapters_use_generic_source_operations(monkeypatch) -> None:
    plugin = CompatibilityPluginStub()
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda _name: plugin)

    schemas = asyncio.run(sources.list_schemas("warehouse"))
    tables = asyncio.run(sources.list_tables_for_schema("warehouse", "dbo"))
    canonical_metadata = asyncio.run(
        sources.get_table_metadata("warehouse", "dbo.Customer")
    )
    compatibility_metadata = asyncio.run(
        sources.get_table_metadata_for_schema("warehouse", "dbo", "Customer")
    )
    canonical_preview = asyncio.run(
        sources.preview("warehouse", "dbo.Customer", limit=3)
    )
    compatibility_preview = asyncio.run(
        sources.preview_for_schema("warehouse", "dbo", "Customer", limit=3)
    )

    assert schemas.items == ["dbo", "sales"]
    assert tables.items[0].name == "Customer"
    assert tables.items[0].description == "Customer master"
    assert compatibility_metadata.model_dump() == canonical_metadata.model_dump()
    assert compatibility_preview.model_dump() == canonical_preview.model_dump()


def test_schema_import_adapter_calls_real_import_pipeline(monkeypatch) -> None:
    saved = []
    imported = []
    wrapper = SimpleNamespace()
    datam8_model = SimpleNamespace(save=lambda locator: saved.append(locator))
    monkeypatch.setattr(factory, "get_model", lambda: datam8_model)

    def import_from_source(data_source, source_location, locator, *, model):
        imported.append((data_source, source_location, locator, model))
        return wrapper

    monkeypatch.setattr(sources.source, "import_from_source", import_from_source)

    result = asyncio.run(
        sources.import_for_schema(
            "warehouse",
            "dbo",
            "Customer",
            sources.CompatibilityImportBody(locator="modelEntities/raw/Customer"),
        )
    )

    assert result is wrapper
    assert imported == [
        (
            "warehouse",
            "dbo.Customer",
            "modelEntities/raw/Customer",
            datam8_model,
        )
    ]
    assert saved == ["modelEntities/raw/Customer"]
