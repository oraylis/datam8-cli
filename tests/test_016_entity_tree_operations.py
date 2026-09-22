from pathlib import Path

from fastapi.testclient import TestClient

from datam8 import factory
from datam8.api.app import create_app
from datam8.model import EntityWrapper, Locator, Model
from datam8.model.model import EntityFileRef
from datam8_model.base import EntityType
from datam8_model.data_type import DataTypeDefinition
from datam8_model.property import PropertyValue


def test_clone_api_is_not_captured_by_create_route(
    model: Model,
    monkeypatch,
) -> None:
    source = next(iter(model.dataTypes.values()))
    target = "dataTypes/CloneRouteRegression"
    monkeypatch.setattr(factory, "get_model", lambda: model)

    response = TestClient(create_app()).put(
        "/entities/clone",
        json={"locator": str(source.locator), "newLocator": target},
    )

    assert response.status_code == 200
    assert model.has_locator(target)


def test_delete_model_entities_also_removes_folders(model: Model) -> None:
    deleted = model.delete_entities("modelEntities/020-Core/Sales/")

    assert any(locator.entityType == EntityType.MODEL_ENTITIES.value for locator in deleted)
    assert any(locator.entityType == EntityType.FOLDERS.value for locator in deleted)
    assert all(model[locator.entityType][locator].is_deleted for locator in deleted)


def test_move_folder_rebases_complete_subtree_and_metadata(model: Model) -> None:
    original_folder = model.folders.get(Locator.from_path("folders/020-Core/Sales"))
    assert original_folder is not None

    moved = model.move_entities(
        "folders/020-Core/Sales",
        "folders/020-Core/SalesRenamed",
    )

    moved_folder = next(
        wrapper
        for wrapper in moved
        if wrapper.locator == Locator.from_path("folders/020-Core/SalesRenamed")
    )

    assert moved_folder.entity.name == "SalesRenamed"
    assert original_folder.is_deleted


def test_add_model_entity_ignores_client_id_and_uses_dedicated_file(model: Model) -> None:
    existing = next(iter(model.modelEntities.values()))
    existing_max = max(wrapper.entity.id for wrapper in model.modelEntities.values())
    payload = existing.entity.model_copy().model_dump(mode="json")
    payload["id"] = 1
    payload["name"] = "ClientProvidedName"
    zone_folder = existing.locator.folders[0]

    created = model.add_entity(
        f"modelEntities/{zone_folder}/CreatedEntity",
        payload,
    )

    assert created.entity.id == existing_max + 1
    assert created.entity.name == "CreatedEntity"
    assert created.source_file == (
        model.get_base_path_for_entity_type(EntityType.MODEL_ENTITIES)
        / zone_folder
        / "CreatedEntity.json"
    )
    assert created.source_file != existing.source_file


def test_property_value_delete_uses_property_and_name(tmp_path: Path) -> None:
    file_path = tmp_path / "PropertyValues.json"
    file_path.write_text(
        """{
  "type": "propertyValues",
  "propertyValues": [
    { "name": "Default", "property": "Color" },
    { "name": "Default", "property": "Status" }
  ]
}
""",
        encoding="utf-8",
    )
    color = Locator.from_path("propertyValues/Color/Default")
    status = Locator.from_path("propertyValues/Status/Default")
    file_ref = EntityFileRef(
        _type=EntityType.PROPERTY_VALUES,
        file_path=file_path,
        locators=[color, status],
    )
    wrapper = EntityWrapper(
        locator=color,
        source_file=file_path,
        entity=PropertyValue(name="Default", property="Color"),
    )

    assert file_ref.delete(wrappers=[wrapper]) is False
    assert file_ref.locators == [status]
    content = file_path.read_text(encoding="utf-8")
    assert '"property": "Color"' not in content
    assert '"property": "Status"' in content


def test_delete_last_collection_entry_removes_file(tmp_path: Path) -> None:
    file_path = tmp_path / "DataTypes.json"
    file_path.write_text(
        """{
  "type": "dataTypes",
  "dataTypes": [
    {"name": "Text", "displayName": "Text", "targets": {"databricks": "string"}}
  ]
}
""",
        encoding="utf-8",
    )
    locator = Locator.from_path("dataTypes/Text")
    file_ref = EntityFileRef(
        _type=EntityType.DATA_TYPES,
        file_path=file_path,
        locators=[locator],
    )
    wrapper = EntityWrapper(
        locator=locator,
        source_file=file_path,
        entity=DataTypeDefinition(
            name="Text",
            displayName="Text",
            targets={"databricks": "string"},
        ),
    )

    assert file_ref.delete(wrappers=[wrapper]) is True
    assert file_ref.locators == []
    assert not file_path.exists()
