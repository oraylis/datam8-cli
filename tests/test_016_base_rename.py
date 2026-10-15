import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app
from datam8.model import Locator


@pytest.fixture
def rename_solution(tmp_path, monkeypatch):
    solution_path = tmp_path / "Rename.dm8s"
    solution_path.write_text(
        json.dumps(
            {
                "schemaVersion": "2.0.0",
                "basePath": "Base",
                "modelPath": "Model",
                "pluginsPath": "Plugins",
                "generatorTargets": [
                    {"name": "test", "sourcePath": "Generate", "outputPath": "Output"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Base").mkdir()
    (tmp_path / "Model").mkdir()
    monkeypatch.setattr(config, "solution_path", solution_path)
    monkeypatch.setattr(config, "solution_folder_path", tmp_path)
    monkeypatch.setattr(config, "lazy", True)
    return solution_path


@pytest.mark.parametrize("custom_path", [False, True], ids=["standard", "custom"])
@pytest.mark.parametrize(
    "entity_type, fields",
    [
        ("properties", {"displayName": "Original"}),
        ("propertyValues", {"property": "write_mode"}),
        ("zones", {"displayName": "Original", "targetName": "original"}),
        ("dataTypes", {"targets": {}}),
        (
            "dataSourceTypes",
            {
                "dataTypeMapping": [{"sourceType": "int", "targetType": "int"}],
                "connectionProperties": [{"name": "host", "type": "string", "required": True}],
                "authModes": [],
            },
        ),
        ("dataProducts", {"dataModules": [{"name": "Module"}]}),
        ("dataModules", {}),
        ("attributeTypes", {"displayName": "Original", "defaultType": "int"}),
        ("dataSources", {"type": "test", "extendedProperties": {}}),
    ],
)
def test_base_rename_preserves_source_file(rename_solution, entity_type, fields, custom_path):
    base_path = rename_solution.parent / "Base"
    filename = f"{entity_type[0].upper()}{entity_type[1:]}.json"
    source = base_path / "Definitions" / "Custom.json" if custom_path else base_path / filename
    source.parent.mkdir(exist_ok=True)
    peer = {"name": "Untouched", **fields}
    source.write_text(
        json.dumps({"type": entity_type, entity_type: [{"name": "Original", **fields}, peer]}),
        encoding="utf-8",
    )
    model = asyncio.run(factory.load_model(rename_solution))
    prefix = f"{entity_type}/write_mode" if entity_type == "propertyValues" else entity_type
    original = Locator.from_path(f"{prefix}/Original")
    renamed_locator = Locator.from_path(f"{prefix}/Renamed")

    renamed = model.rename_entity(original, "Renamed")

    assert renamed.source_file == source
    # Multiple edits before the next save must still replace the original row.
    renamed = model.rename_entity(renamed_locator, "Final")
    renamed_locator = Locator.from_path(f"{prefix}/Final")
    model.save()
    assert json.loads(source.read_text())[entity_type] == [{"name": "Final", **fields}, peer]
    assert list(base_path.rglob("*.json")) == [source]
    assert original not in model[entity_type]
    assert set(model._model_files[source].locators) == {
        renamed_locator,
        Locator.from_path(f"{prefix}/Untouched"),
    }
    assert model._model_files[source].renamed_locators == {}
    assert model.get_unsaved_entities() == ([], [])

    # Reusing the old name must work after saving, without stale rename bookkeeping.
    model.rename_entity(renamed_locator, "Original")
    model.save()
    reloaded = asyncio.run(factory.load_model(rename_solution))
    assert reloaded[entity_type][original].source_file == source
    assert renamed_locator not in reloaded[entity_type]
    assert len(reloaded[entity_type]) == 2


def test_property_value_rename_api_preserves_other_properties(rename_solution, monkeypatch):
    source = rename_solution.parent / "Base" / "PropertyValues.json"
    peers = [
        {"property": "other", "name": "Default"},
        {"property": "other", "name": "Renamed"},
        {"property": "write_mode", "name": "Existing"},
    ]
    source.write_text(
        json.dumps(
            {
                "type": "propertyValues",
                "propertyValues": [{"property": "write_mode", "name": "Default"}, *peers],
            }
        ),
        encoding="utf-8",
    )
    entity_path = rename_solution.parent / "Model" / "Customer.json"
    entity_path.write_text(
        json.dumps(
            {
                "id": 1,
                "name": "Customer",
                "attributes": [
                    {
                        "ordinalNumber": 1,
                        "name": "Id",
                        "attributeType": "ID",
                        "dataType": {"type": "int", "nullable": False},
                        "history": "SCD0",
                        "dateAdded": "2026-01-01T00:00:00Z",
                    }
                ],
                "sources": [],
                "transformations": [],
                "relationships": [],
                "properties": [{"property": "write_mode", "value": "Default"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(factory, "_model", asyncio.run(factory.load_model(rename_solution)))
    client = TestClient(create_app())

    for old_name, new_name in [("Default", "Renamed"), ("Renamed", "Default")]:
        response = client.post(
            "/entities/rename",
            json={"from": f"propertyValues/write_mode/{old_name}", "to": new_name},
        )
        assert response.status_code == 200, response.text
        assert client.post("/model/save").status_code == 204
        assert json.loads(source.read_text())["propertyValues"] == [
            {"property": "write_mode", "name": new_name},
            *peers,
        ]
        assert json.loads(entity_path.read_text())["properties"] == [
            {"property": "write_mode", "value": new_name}
        ]
        assert client.post("/model/reload").status_code == 200
        assert factory.get_model().get_unsaved_entities() == ([], [])

    # A normal update must also distinguish equal value names across properties.
    response = client.patch(
        "/entities/propertyValues/write_mode/Default", json={"displayName": "Updated"}
    )
    assert response.status_code == 200
    assert client.post("/model/save").status_code == 204
    rows = json.loads(source.read_text())["propertyValues"]
    assert rows[0]["displayName"] == "Updated"
    assert rows[1:] == peers
    assert list(source.parent.rglob("*.json")) == [source]


def test_base_move_to_different_folder_still_changes_source(rename_solution):
    source = rename_solution.parent / "Base" / "Custom.json"
    source.write_text(
        json.dumps({"type": "dataTypes", "dataTypes": [{"name": "Text", "targets": {}}]}),
        encoding="utf-8",
    )
    model = asyncio.run(factory.load_model(rename_solution))

    moved = model.move_entity(
        Locator.from_path("dataTypes/Text"), Locator.from_path("dataTypes/Archive/Text")
    )
    model.save()

    target = source.parent / "Archive" / "DataTypes.json"
    assert moved.source_file == target
    assert target.is_file()
    assert not source.exists()
