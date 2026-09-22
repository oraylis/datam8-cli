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
                    "properties": [{"property": "classification", "value": "restricted"}],
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
        ),
        SourceObject(name="dummy", type="dummy"),
    )
    assert next(metadata.iter_source_fields()).description is None
