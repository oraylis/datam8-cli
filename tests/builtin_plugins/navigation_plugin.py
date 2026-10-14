"""Offline provider for UI/backend tests of opaque handles and optional descriptions."""

import polars as pl

from datam8.plugins.base import TableMetadata
from datam8.plugins.builtins.file import CsvFile
from datam8_model.data_source import SourceDataTypeMapping, SourceObject
from datam8_model.model import ModelAttributeMapping, ModelRelationship, ModelTransformation
from datam8_model.plugin import Capability, PluginManifest


class DescribedMetadata(TableMetadata):
    def apply_import_metadata(self, entity):
        entity.displayName = "Provider business name"
        entity.attributes[0].displayName = "Provider column name"
        entity.relationships = [
            ModelRelationship(
                targetLocation=123,
                attributes=[ModelAttributeMapping(sourceName="id", targetName="id")],
            )
        ]
        entity.transformations = [
            ModelTransformation(stepNo=1, kind="builtin", name="Provided transformation")
        ]


class GenericProvider(CsvFile):
    @classmethod
    def manifest(cls):
        return PluginManifest(
            id="provider-alpha",
            displayName="Generic test provider",
            version="1.0.0",
            entryPoint="navigation_plugin.py:GenericProvider",
            capabilities=[
                Capability.METADATA,
                Capability.PREVIEW_DATA,
                Capability.VALIDATION_CONNECTION,
            ],
        )

    @staticmethod
    def get_data_type_mappings():
        return [SourceDataTypeMapping(sourceType="BIGINT", targetType="long")]

    @classmethod
    def resolve_source_type(cls, source_type):
        raise AssertionError("Imports must use persisted mappings, not the plugin resolver")

    def get_source_capabilities(self):
        return {
            "listSource": self.extended_properties.get("listed", True),
            "metadata": True,
            "previewData": self.extended_properties.get("preview", False),
        }

    def list_source(self, source_location=None, /):
        if source_location is None:
            rows = [{"name": "Folder", "type": "CONTAINER", "sourceLocation": "opaque:root"}]
        elif source_location == "opaque:root":
            rows = [{"name": "Nested", "type": "DIRECTORY", "sourceLocation": "opaque#depth"}]
        else:
            rows = [
                {
                    "name": "suggested_provider_name",
                    "type": "OBJECT",
                    "sourceLocation": "object?schema#42",
                    "description": "Listing description",
                }
            ]
        return pl.DataFrame(rows)

    def get_table_metadata(self, source_location, /):
        described = self.extended_properties.get("described", False)
        cls = DescribedMetadata if described else TableMetadata
        return cls(
            pl.DataFrame(
                [
                    {
                        "name": "id",
                        "ordinal": 1,
                        "dataType": "BIGINT",
                        "isNullable": False,
                    }
                ]
            ),
            SourceObject(
                name="suggested_provider_name",
                type="OBJECT",
                description="Provider metadata description",
                sourceOverride={"sourceLocation": "read?object#42"},
            ),
        )

    def get_sources(self, source_location, /):
        return (
            [{"sourceLocation": "read?object#42", "sourceName": "id", "targetName": "id"}]
            if self.extended_properties.get("described", False)
            else None
        )

    def preview_data(self, source_location, *, limit=10):
        return pl.DataFrame({"id": [1]}).head(limit).lazy()
