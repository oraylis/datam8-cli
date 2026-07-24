# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from types import SimpleNamespace

import polars as pl

from datam8 import factory, source
from datam8.plugins.base import TableMetadata
from datam8.plugins.builtins.file import CsvFile
from datam8.plugins.builtins.sql_server import SqlServer
from datam8_model.data_source import SourceObject, SourceOverride
from datam8_model.plugin import Capability


class AttributeTypesStub:
    def get_many_where(self, predicate):
        wrapper = SimpleNamespace(
            entity=SimpleNamespace(
                name="Generic String",
                defaultType="string",
                isDefaultProperty=True,
            )
        )
        return [wrapper] if predicate(wrapper) else []


class SourceModelStub:
    attributeTypes = AttributeTypesStub()


class SourcePluginStub:
    def get_table_metadata(self, _source_location: str) -> TableMetadata:
        metadata = pl.DataFrame(
            [
                {
                    "name": "customer_id",
                    "ordinal": 1,
                    "dataType": "varchar",
                    "isNullable": False,
                    "isPrimaryKey": True,
                    "description": "Technical customer key",
                    "properties": [
                        {"property": "classification", "value": "restricted"}
                    ],
                }
            ]
        )
        source_object = SourceObject(
            name="customers",
            type="TABLE",
            description="Customer master",
            properties=[{"property": "domain", "value": "sales"}],
            sourceOverride=SourceOverride(
                dataSource="crm-api",
                sourceLocation="customers/current",
            ),
        )
        return TableMetadata(metadata, source_object)

    def resolve_source_type(self, _source_type: str) -> str:
        return "string"


def test_source_metadata_and_override_reach_model_entity(monkeypatch) -> None:
    plugin = SourcePluginStub()
    monkeypatch.setattr(
        factory,
        "get_plugin_for_data_source",
        lambda _data_source, model: plugin,
    )

    entity = source.read_from_data_source(
        "sql-crm",
        "dbo.customers",
        model=SourceModelStub(),  # type: ignore[arg-type]
    )

    assert entity.description == "Customer master"
    assert entity.properties is not None
    assert entity.properties[0].property == "domain"
    assert entity.attributes[0].description == "Technical customer key"
    assert entity.attributes[0].properties is not None
    assert entity.sources[0].dataSource == "crm-api"
    assert entity.sources[0].sourceLocation == "customers/current"


def test_builtin_preview_implementations_advertise_capability() -> None:
    for plugin_class in (CsvFile, SqlServer):
        assert Capability.PREVIEW_DATA in plugin_class.manifest().capabilities


def test_table_metadata_defaults_description_to_none() -> None:
    metadata = TableMetadata(
        pl.DataFrame(
            [
                {
                    "name": "id",
                    "ordinal": 1,
                    "dataType": "int",
                    "isNullable": False,
                }
            ]
        )
    )
    assert next(metadata.iter_source_fields()).description is None
