"""Offline example connector for the current DataM8 Python plugin interface."""

import polars as pl

from datam8.plugins.base import METADATA, UI_SCHEMA, VALIDATION_CONNECTION, Plugin, TableMetadata
from datam8_model.data_source import (
    AuthMode,
    ConnectionProperty,
    ConnectionPropertyValueType,
    SourceDataTypeMapping,
    SourceObject,
)
from datam8_model.plugin import PluginManifest


class ExamplePlugin(Plugin):
    @classmethod
    def manifest(cls) -> PluginManifest:
        return PluginManifest(
            id="example:Static",
            displayName="Static example",
            version="1.0.0",
            entryPoint="static_example/plugin.py:ExamplePlugin",
            capabilities=[METADATA, UI_SCHEMA, VALIDATION_CONNECTION],
        )

    @classmethod
    def resolve_source_type(cls, source_type: str, /) -> str:
        # Required by the ABC, but current import/refresh uses saved mappings.
        raise NotImplementedError("Configure type mappings on the Data Source Type.")

    @staticmethod
    def parse_source_location(source_location: str) -> tuple[str, ...]:
        if source_location != "demo:customers":
            raise ValueError(f"Unknown example object: {source_location}")
        return ("customers",)

    @staticmethod
    def get_auth_modes() -> list[AuthMode]:
        return [AuthMode(name="no_auth", required=["dataset"])]

    @staticmethod
    def get_connection_properties() -> list[ConnectionProperty]:
        return [
            ConnectionProperty(
                name="dataset",
                type=ConnectionPropertyValueType.STRING,
                required=True,
                default="customers",
            )
        ]

    @staticmethod
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        return [
            SourceDataTypeMapping(sourceType="BIGINT", targetType="long"),
            SourceDataTypeMapping(sourceType="nvarchar", targetType="string"),
            SourceDataTypeMapping(sourceType="DECIMAL", targetType="decimal"),
        ]

    def test_connection(self) -> Exception | None:
        if self.extended_properties["dataset"] != "customers":
            return ValueError("The example supports only the customers dataset.")
        return None

    def list_source(self, source_location: str | None = None, /) -> pl.DataFrame:
        if source_location is not None:
            self.parse_source_location(source_location)
        return pl.DataFrame(
            [{"name": "customers", "type": "TABLE", "sourceLocation": "demo:customers"}]
        )

    def get_table_metadata(self, source_location: str, /) -> TableMetadata:
        self.parse_source_location(source_location)
        return TableMetadata(
            pl.DataFrame(
                {
                    "name": ["id", "title", "amount"],
                    "ordinal": [1, 2, 3],
                    "dataType": ["BIGINT", "nvarchar", "DECIMAL"],
                    "isNullable": [False, True, True],
                    "isPrimaryKey": [True, False, False],
                    "maxLength": [None, 62, None],
                    "numericPrecision": [None, None, 18],
                    "numericScale": [None, None, 0],
                }
            ),
            SourceObject(name="customers", type="TABLE", description="Offline example"),
        )
