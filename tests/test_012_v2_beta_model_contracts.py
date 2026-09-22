# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from pathlib import Path

import pytest
from pydantic import ValidationError

from datam8.model import EntityRepository, EntityWrapper, Locator, Model
from datam8_model import base as b
from datam8_model import data_type as dt
from datam8_model import model as m
from datam8_model import solution as s


def test_model_relationship_accepts_internal_and_external_targets() -> None:
    attributes = [m.ModelAttributeMapping(sourceName="CustomerId", targetName="Id")]

    internal = m.ModelRelationship(targetLocation=1, attributes=attributes)
    external = m.ModelRelationship(
        dataSource="crm",
        targetLocation="dbo.Customer",
        attributes=attributes,
    )

    assert internal.targetLocation == 1
    assert external.targetLocation == "dbo.Customer"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "dataSource": "crm",
            "targetLocation": 1,
            "attributes": [{"sourceName": "CustomerId", "targetName": "Id"}],
        },
        {
            "targetLocation": "dbo.Customer",
            "attributes": [{"sourceName": "CustomerId", "targetName": "Id"}],
        },
        {
            "dataSource": "crm",
            "targetLocation": "",
            "attributes": [{"sourceName": "CustomerId", "targetName": "Id"}],
        },
    ],
)
def test_model_relationship_rejects_mismatched_targets(payload: dict) -> None:
    with pytest.raises(ValidationError):
        m.ModelRelationship.model_validate(payload)


def test_rename_base_entity_replaces_original_json_entry(tmp_path: Path, monkeypatch) -> None:
    source_file = tmp_path / "DataTypes.json"
    source_file.write_text(
        """{
  "type": "dataTypes",
  "dataTypes": [
    {"name": "Text", "displayName": "Text", "targets": {"databricks": "string"}},
    {"name": "Number", "displayName": "Number", "targets": {"databricks": "int"}}
  ]
}
""",
        encoding="utf-8",
    )
    old_locator = Locator.from_path("dataTypes/Text")
    new_locator = Locator.from_path("dataTypes/String")
    wrapper = EntityWrapper(
        locator=old_locator,
        source_file=source_file,
        entity=dt.DataTypeDefinition(
            name="Text",
            displayName="Text",
            targets={"databricks": "string"},
        ),
        resolved=True,
    )
    data_types = EntityRepository({old_locator: wrapper}, b.EntityType.DATA_TYPES.value)
    model_entities = EntityRepository({}, b.EntityType.MODEL_ENTITIES.value)
    solution = s.Solution(
        schemaVersion="2.0.0",
        modelPath=Path("Model"),
        basePath=Path("."),
        pluginsPath=Path("Plugins"),
        generatorTargets=[
            s.GeneratorTarget(
                name="test",
                sourcePath=Path("Generate"),
                outputPath=Path("Output"),
            )
        ],
    )
    monkeypatch.setattr("datam8.config.solution_folder_path", tmp_path)
    model = Model(
        solution,
        dataTypes=data_types,
        modelEntities=model_entities,
        properties=EntityRepository({}, b.EntityType.PROPERTIES.value),
        propertyValues=EntityRepository({}, b.EntityType.PROPERTY_VALUES.value),
        zones=EntityRepository({}, b.EntityType.ZONES.value),
        dataSourceTypes=EntityRepository({}, b.EntityType.DATA_SOURCE_TYPES.value),
        dataProducts=EntityRepository({}, b.EntityType.DATA_PRODUCTS.value),
        dataModules=EntityRepository({}, b.EntityType.DATA_MODULES.value),
        attributeTypes=EntityRepository({}, b.EntityType.ATTRIBUTE_TYPES.value),
        dataSources=EntityRepository({}, b.EntityType.DATA_SOURCES.value),
        folders=EntityRepository({}, b.EntityType.FOLDERS.value),
    )
    model.update_file_reference(
        _type=b.EntityType.DATA_TYPES,
        file_path=source_file,
        locators=[old_locator, Locator.from_path("dataTypes/Number")],
    )

    renamed = model.rename_entity(old_locator, "String")
    model._model_files[source_file].update(wrappers=[renamed])

    assert model.dataTypes[old_locator].is_deleted
    assert new_locator in model.dataTypes
    assert renamed.entity.name == "String"
    content = source_file.read_text(encoding="utf-8")
    assert '"name": "Text"' not in content
    assert '"name": "String"' in content
    assert '"name": "Number"' in content
