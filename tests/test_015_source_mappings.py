# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.

import asyncio
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from datam8 import factory, source
from datam8.api.routes.sources import get_import_description
from datam8.model import EntityRepository, EntityWrapper, Locator
from datam8.plugins.base import TableMetadata
from datam8_model import attribute as at
from datam8_model import data_type as dt
from datam8_model import model as m
from datam8_model import property as p
from datam8_model.data_source import SourceObject


def test_sources_from_definitions_groups_mappings_and_properties() -> None:
    definitions = [
        {
            "sourceLocation": "customers",
            "sourceName": "customer_id",
            "targetName": "id",
            "sourceDataType": {"type": "int", "nullable": False},
            "sourceProperties": [{"property": "system", "value": "crm"}],
            "mappingProperties": [{"property": "extract_mode", "value": "delta"}],
        },
        {
            "sourceLocation": "customers",
            "sourceName": "name",
            "targetName": "displayName",
        },
        {
            "sourceLocation": "orders",
            "sourceName": "order_id",
            "targetName": "lastOrder",
            "sourceAlias": "sales",
        },
    ]

    sources = source._sources_from_definitions(definitions, "crm")

    assert [(item.sourceLocation, item.sourceAlias) for item in sources] == [
        ("customers", None),
        ("orders", "sales"),
    ]
    assert [(item.sourceName, item.targetName) for item in sources[0].mapping or []] == [
        ("customer_id", "id"),
        ("name", "displayName"),
    ]
    assert sources[0].properties is not None
    assert sources[0].properties[0].property == "system"
    assert sources[0].mapping[0].properties[0].value == "delta"
    assert sources[0].mapping[0].sourceDataType.type == "int"


def test_sources_from_definitions_keeps_contract_metadata_locations_separate() -> None:
    definitions = [
        {
            "sourceLocation": "bronze.accounts",
            "sourceName": "root_subscriber_id",
            "targetName": "subscriber_id",
            "metadataLocation": "contract-a#subscriber_id",
        },
        {
            "sourceLocation": "bronze.accounts",
            "sourceName": "subscriber_id",
            "targetName": "subscriber_id",
            "metadataLocation": "contract-b#subscriber_id",
        },
    ]

    sources = source._sources_from_definitions(definitions, "odcs")

    assert [item.metadataLocation for item in sources] == [
        "contract-a#subscriber_id",
        "contract-b#subscriber_id",
    ]
    assert [item.mapping[0].sourceName for item in sources] == [
        "root_subscriber_id",
        "subscriber_id",
    ]


def test_empty_source_definitions_remove_all_external_sources() -> None:
    assert source._sources_from_definitions([], "odcs") == []


def test_source_properties_may_be_defined_on_one_mapping_row() -> None:
    definitions = [
        {
            "sourceLocation": "customers",
            "sourceName": "id",
            "targetName": "id",
            "sourceProperties": [{"property": "system", "value": "crm"}],
        },
        {"sourceLocation": "customers", "sourceName": "name", "targetName": "name"},
    ]

    sources = source._sources_from_definitions(definitions, "crm")

    assert sources[0].properties[0].property == "system"


def test_source_properties_must_not_conflict_within_source() -> None:
    definitions = [
        {
            "sourceLocation": "customers",
            "sourceName": "id",
            "targetName": "id",
            "sourceProperties": [{"property": "system", "value": "crm"}],
        },
        {
            "sourceLocation": "customers",
            "sourceName": "name",
            "targetName": "name",
            "sourceProperties": [{"property": "system", "value": "erp"}],
        },
    ]

    with pytest.raises(ValueError, match="Conflicting sourceProperties"):
        source._sources_from_definitions(definitions, "crm")


def test_sources_from_definitions_rejects_duplicate_mappings() -> None:
    definitions = [
        {"sourceLocation": "customers", "sourceName": "id", "targetName": "id"},
        {"sourceLocation": "customers", "sourceName": "id", "targetName": "id"},
    ]

    with pytest.raises(ValueError, match="Duplicate source mapping"):
        source._sources_from_definitions(definitions, "crm")


def test_sources_from_definitions_rejects_invalid_mapping_properties() -> None:
    definitions = [
        {
            "sourceLocation": "customers",
            "sourceName": "id",
            "targetName": "id",
            "mappingProperties": "delta",
        }
    ]

    with pytest.raises(ValueError, match="mappingProperties must be a list"):
        source._sources_from_definitions(definitions, "crm")


def test_source_only_uses_plugin_sources_without_reading_metadata(monkeypatch) -> None:
    class SourcesOnlyPlugin:
        def get_sources(self, _source_location: str) -> list[dict[str, str]]:
            return [{"sourceLocation": "physical", "sourceName": "id", "targetName": "id"}]

        def get_table_metadata(self, _source_location: str) -> None:
            raise AssertionError("Source-only must not read attribute metadata")

    monkeypatch.setattr(
        factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: SourcesOnlyPlugin()
    )
    refreshed = source.read_external_sources("crm", "logical", model=SimpleNamespace())

    assert refreshed[0].sourceLocation == "physical"
    assert refreshed[0].metadataLocation is None


def test_default_source_refresh_preserves_existing_properties() -> None:
    existing = m.ExternalModelSource(
        dataSource="crm",
        sourceAlias="primary",
        sourceLocation="customers",
        properties=[p.PropertyReference(property="extract_mode", value="delta")],
        mapping=[
            m.SourceAttributeMapping(
                sourceName="id",
                targetName="id",
                properties=[p.PropertyReference(property="extract_mode", value="delta")],
            )
        ],
    )
    mappings = [m.SourceAttributeMapping(sourceName="id", targetName="id")]

    refreshed = source._default_source("crm", "customers", mappings, existing_source=existing)

    assert refreshed[0].sourceAlias == "primary"
    assert refreshed[0].properties == existing.properties
    assert refreshed[0].mapping[0].properties == existing.mapping[0].properties


class SourcePluginStub:
    def get_table_metadata(self, _source_location: str) -> TableMetadata:
        return TableMetadata(
            pl.DataFrame(
                [
                    {
                        "name": "customer_id",
                        "ordinal": 1,
                        "dataType": "varchar",
                        "isNullable": False,
                    },
                    {
                        "name": "first_name",
                        "ordinal": 2,
                        "dataType": "varchar",
                        "isNullable": True,
                    },
                ]
            ),
            SourceObject(
                name="customer_view",
                type="VIEW",
                properties=[p.PropertyReference(property="domain", value="sales")],
            ),
        )

    def resolve_source_type(self, _source_type: str) -> str:
        return "string"

    def get_sources(self, _source_location: str) -> list[dict]:
        return [
            {
                "sourceLocation": "customer_core",
                "sourceName": "customer_id",
                "targetName": "id",
                "sourceAlias": "core",
                "sourceProperties": [{"property": "layer", "value": "raw"}],
            },
            {
                "sourceLocation": "customer_details",
                "sourceName": "first_name",
                "targetName": "firstName",
                "sourceAlias": "details",
                "sourceProperties": [
                    {"property": "layer", "value": "raw"},
                    {"property": "sensitivity", "value": "internal"},
                ],
            },
        ]


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


def test_read_from_data_source_uses_plugin_sources_and_import_location(monkeypatch) -> None:
    monkeypatch.setattr(
        factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: SourcePluginStub()
    )
    model = SimpleNamespace(attributeTypes=AttributeTypesStub())

    entity = source.read_from_data_source("crm", "customer_view", model=model)

    assert {item.metadataLocation for item in entity.sources} == {"customer_view"}
    assert [source.sourceLocation for source in entity.sources] == [
        "customer_core",
        "customer_details",
    ]
    assert [source.sourceAlias for source in entity.sources] == ["core", "details"]
    assert entity.properties[0].value == "sales"
    assert entity.sources[0].properties[0].value == "raw"
    assert entity.sources[1].properties[1].value == "internal"
    assert entity.sources[0].mapping[0].targetName == "id"
    assert entity.sources[1].mapping[0].targetName == "firstName"


def test_import_description_exposes_plugin_entity(monkeypatch) -> None:
    model = SimpleNamespace(attributeTypes=AttributeTypesStub())
    monkeypatch.setattr(factory, "get_model", lambda: model)
    monkeypatch.setattr(
        factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: SourcePluginStub()
    )

    response = asyncio.run(get_import_description("crm", "customer_view"))

    assert response.entity is not None
    assert {item.metadataLocation for item in response.entity.sources} == {"customer_view"}
    assert len(response.entity.sources) == 2


def test_import_description_without_source_definitions(monkeypatch) -> None:
    plugin = SimpleNamespace(get_sources=lambda _location: None)
    monkeypatch.setattr(factory, "get_model", lambda: SimpleNamespace())
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)

    response = asyncio.run(get_import_description("crm", "customer_view"))

    assert response.entity is None


def _attribute(name: str, ordinal: int) -> at.Attribute:
    return at.Attribute(
        ordinalNumber=ordinal,
        name=name,
        attributeType="Generic String",
        dataType=dt.DataType(type="string", nullable=True),
        dateAdded="2026-01-01T00:00:00Z",
    )


def _source_model() -> tuple[SimpleNamespace, str, m.ModelEntity]:
    locator = "modelEntities/test/customer"
    entity = m.ModelEntity(
        id=1,
        name="customer",
        attributes=[_attribute("id", 1), _attribute("computedName", 2)],
        properties=[p.PropertyReference(property="domain", value="old")],
        sources=[
            m.ExternalModelSource(
                dataSource="test",
                sourceLocation="old_location",
                metadataLocation="customer_view",
                mapping=[m.SourceAttributeMapping(sourceName="old_id", targetName="id")],
            )
        ],
        transformations=[],
        relationships=[],
    )
    wrapper = EntityWrapper(
        locator=Locator.from_path(locator),
        source_file=Path("customer.json"),
        entity=entity,
        resolved=True,
    )
    repository = EntityRepository({wrapper.locator: wrapper}, "modelEntities")
    return SimpleNamespace(modelEntities=repository), locator, entity


def _refreshed_sources() -> list[m.ExternalModelSource]:
    return [
        m.ExternalModelSource(
            dataSource="test",
            sourceLocation="customer_core_v2",
            metadataLocation="customer_view",
            sourceAlias="core",
            properties=[p.PropertyReference(property="layer", value="curated")],
            mapping=[m.SourceAttributeMapping(sourceName="customer_id", targetName="id")],
        )
    ]


def test_source_only_refresh_preserves_entity_attributes_and_properties(monkeypatch) -> None:
    model, locator, original = _source_model()
    monkeypatch.setattr(
        source, "read_external_sources", lambda *_args, **_kwargs: _refreshed_sources()
    )

    wrapper, _diff = source.compare_entity_with_source(locator, model=model, mode="sources-only")

    assert wrapper.entity.sources[0].sourceLocation == "customer_core_v2"
    assert wrapper.entity.sources[0].properties[0].value == "curated"
    assert [attribute.name for attribute in wrapper.entity.attributes] == [
        attribute.name for attribute in original.attributes
    ]
    assert wrapper.entity.properties[0].value == "old"


def test_complete_refresh_updates_entity_properties_and_sources(monkeypatch) -> None:
    model, locator, original = _source_model()
    model.modelEntities[locator].entity.properties.append(
        p.PropertyReference(property="jobs", value="daily_12")
    )
    refreshed = m.ModelEntity(
        id=1,
        name="customer",
        attributes=[_attribute("id", 1), _attribute("firstName", 2)],
        properties=[p.PropertyReference(property="domain", value="new")],
        sources=_refreshed_sources(),
        transformations=[],
        relationships=[],
    )
    monkeypatch.setattr(source, "read_from_data_source", lambda *_args, **_kwargs: refreshed)

    wrapper, _diff = source.compare_entity_with_source(locator, model=model)

    assert {prop.property: prop.value for prop in wrapper.entity.properties} == {
        "domain": "new",
        "jobs": "daily_12",
    }
    assert wrapper.entity.sources[0].sourceLocation == "customer_core_v2"
    assert [attribute.name for attribute in wrapper.entity.attributes] == [
        "id",
        "computedName",
        "firstName",
    ]


def test_complete_refresh_preserves_entity_properties_when_plugin_does_not_supply_them(
    monkeypatch,
) -> None:
    model, locator, original = _source_model()
    refreshed = m.ModelEntity(
        id=1,
        name="customer",
        attributes=[_attribute("id", 1)],
        properties=None,
        sources=_refreshed_sources(),
        transformations=[],
        relationships=[],
    )
    monkeypatch.setattr(source, "read_from_data_source", lambda *_args, **_kwargs: refreshed)

    wrapper, _diff = source.compare_entity_with_source(locator, model=model)

    assert wrapper.entity.properties == original.properties


def test_complete_refresh_updates_existing_attribute_properties(monkeypatch) -> None:
    model, locator, original = _source_model()
    refreshed_attribute = _attribute("id", 1)
    refreshed_attribute.description = "new description"
    refreshed_attribute.properties = [p.PropertyReference(property="attribute_type", value="bk")]
    refreshed = m.ModelEntity(
        id=1,
        name="customer",
        attributes=[refreshed_attribute],
        properties=[p.PropertyReference(property="write_mode", value="partition_replace")],
        sources=_refreshed_sources(),
        transformations=[],
        relationships=[],
    )
    monkeypatch.setattr(source, "read_from_data_source", lambda *_args, **_kwargs: refreshed)

    wrapper, _diff = source.compare_entity_with_source(locator, model=model)

    assert wrapper.entity.attributes[0].description == "new description"
    assert wrapper.entity.attributes[0].properties[0].value == "bk"
    assert wrapper.entity.attributes[0].dateAdded == original.attributes[0].dateAdded
    assert {prop.property: prop.value for prop in wrapper.entity.properties} == {
        "domain": "old",
        "write_mode": "partition_replace",
    }
    assert [attribute.name for attribute in wrapper.entity.attributes] == ["id", "computedName"]


def test_complete_refresh_diff_omits_derived_date_modified(monkeypatch) -> None:
    model, locator, _original = _source_model()
    refreshed = m.ModelEntity(
        id=1,
        name="customer",
        attributes=[_attribute("id", 1)],
        properties=[],
        sources=_refreshed_sources(),
        transformations=[],
        relationships=[],
    )
    refreshed.attributes[0].description = "updated from source"
    monkeypatch.setattr(source, "read_from_data_source", lambda *_args, **_kwargs: refreshed)

    wrapper, diff = source.compare_entity_with_source(locator, model=model)

    assert wrapper.entity.attributes[0].dateModified is not None
    assert "description" in str(diff)
    assert "dateModified" not in str(diff)


def test_complete_refresh_does_not_change_unchanged_string_enum_attribute(monkeypatch) -> None:
    model, locator, original = _source_model()
    original.attributes[0].expressionLanguage = "sql"
    refreshed = original.model_copy(deep=True)
    refreshed.attributes[0].expressionLanguage = at.ExpressionLanguage.SQL
    monkeypatch.setattr(source, "read_from_data_source", lambda *_args, **_kwargs: refreshed)

    wrapper, diff = source.compare_entity_with_source(locator, model=model)

    assert not wrapper._changed
    assert diff == {}
    assert wrapper.entity.attributes[0].dateModified is None


class MultiContractPlugin:
    def __init__(self, *, conflicting: bool = False, conflicting_attribute: bool = False) -> None:
        self.source_calls: list[str] = []
        self.metadata_calls: list[str] = []
        self.conflicting = conflicting
        self.conflicting_attribute = conflicting_attribute

    def get_sources(self, location: str) -> list[dict]:
        self.source_calls.append(location)
        if location == "contract_a":
            return [
                {
                    "sourceLocation": "core",
                    "sourceName": "key",
                    "targetName": "id",
                    "sourceAlias": "core",
                    "sourceProperties": [{"property": "layer", "value": "raw"}],
                },
                {
                    "sourceLocation": "details",
                    "sourceName": "label",
                    "targetName": "name",
                    "sourceAlias": "details",
                    "mappingProperties": [{"property": "mode", "value": "delta"}],
                },
            ]
        return [
            {
                "sourceLocation": "events",
                "sourceName": "code",
                "targetName": "code",
                "sourceProperties": [{"property": "layer", "value": "curated"}],
            }
        ]

    def get_table_metadata(self, location: str) -> TableMetadata:
        self.metadata_calls.append(location)
        names = (
            ["id", "name"]
            if location == "contract_a"
            else ["id"]
            if self.conflicting_attribute
            else ["code"]
        )
        return TableMetadata(
            pl.DataFrame(
                [
                    {
                        "name": name,
                        "ordinal": index,
                        "dataType": "varchar",
                        "isNullable": False,
                        "description": "different"
                        if self.conflicting_attribute and location == "contract_b"
                        else None,
                    }
                    for index, name in enumerate(names, start=1)
                ]
            ),
            SourceObject(
                name=location,
                type="DATA_CONTRACT",
                properties=[
                    p.PropertyReference(
                        property="domain" if self.conflicting else location,
                        value=location,
                    )
                ],
            ),
        )

    def resolve_source_type(self, _source_type: str) -> str:
        return "string"


def _multi_contract_model() -> tuple[SimpleNamespace, str]:
    model, locator, _entity = _source_model()
    model.modelEntities[locator].entity.sources = [
        m.ExternalModelSource(
            dataSource="test",
            sourceLocation="old_core",
            metadataLocation="contract_a",
            properties=[p.PropertyReference(property="manual", value="remove")],
            mapping=[m.SourceAttributeMapping(sourceName="old", targetName="id")],
        ),
        m.ExternalModelSource(
            dataSource="test",
            sourceLocation="old_details",
            metadataLocation="contract_a",
            mapping=[m.SourceAttributeMapping(sourceName="label", targetName="name")],
        ),
        m.ExternalModelSource(
            dataSource="test",
            sourceLocation="old_events",
            metadataLocation="contract_b",
            mapping=[m.SourceAttributeMapping(sourceName="code", targetName="code")],
        ),
    ]
    model.attributeTypes = AttributeTypesStub()
    return model, locator


def test_source_only_refreshes_each_contract_once_and_removes_manual_properties(
    monkeypatch,
) -> None:
    model, locator = _multi_contract_model()
    plugin = MultiContractPlugin()
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)

    wrapper, _diff = source.compare_entity_with_source(locator, model=model, mode="sources-only")

    assert plugin.source_calls == ["contract_a", "contract_b"]
    assert plugin.metadata_calls == []
    assert [(item.sourceLocation, item.metadataLocation) for item in wrapper.entity.sources] == [
        ("core", "contract_a"),
        ("details", "contract_a"),
        ("events", "contract_b"),
    ]
    assert wrapper.entity.sources[0].properties[0].property == "layer"
    assert wrapper.entity.sources[1].mapping[0].properties[0].value == "delta"
    assert [attr.name for attr in wrapper.entity.attributes] == ["id", "computedName"]
    assert wrapper.entity.properties[0].value == "old"


def test_complete_refresh_merges_multiple_contracts(monkeypatch) -> None:
    model, locator = _multi_contract_model()
    plugin = MultiContractPlugin()
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)

    wrapper, _diff = source.compare_entity_with_source(locator, model=model)

    assert plugin.source_calls == ["contract_a", "contract_b"]
    assert plugin.metadata_calls == ["contract_a", "contract_b"]
    assert [attr.name for attr in wrapper.entity.attributes] == [
        "id",
        "computedName",
        "name",
        "code",
    ]
    assert {prop.property for prop in wrapper.entity.properties} == {
        "contract_a",
        "contract_b",
        "domain",
    }


def test_complete_refresh_rejects_conflicting_entity_properties(monkeypatch) -> None:
    model, locator = _multi_contract_model()
    plugin = MultiContractPlugin(conflicting=True)
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)

    with pytest.raises(ValueError, match="Conflicting entity property: domain"):
        source.compare_entity_with_source(locator, model=model)


def test_complete_refresh_rejects_conflicting_attributes(monkeypatch) -> None:
    model, locator = _multi_contract_model()
    plugin = MultiContractPlugin(conflicting_attribute=True)
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)

    with pytest.raises(ValueError, match="Conflicting attribute: id"):
        source.compare_entity_with_source(locator, model=model)


def test_external_source_without_metadata_location_round_trips() -> None:
    legacy = m.ExternalModelSource.model_validate({"dataSource": "test", "sourceLocation": "table"})

    assert legacy.metadataLocation is None
    assert "metadataLocation" not in legacy.model_dump(exclude_none=True)
    assert m.ExternalModelSource.model_validate(legacy.model_dump()).metadataLocation is None
