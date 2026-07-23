from pathlib import Path

from datam8.model import EntityWrapper, Locator, Model
from datam8.model.model import EntityFileRef
from datam8_model.base import EntityType
from datam8_model.property import PropertyValue


def test_delete_folder_marks_folder_descendants_and_model_entities(model: Model) -> None:
    deleted = model.delete_entities("folders/020-Core/Sales")

    assert Locator.from_path("folders/020-Core/Sales") in deleted
    assert any(
        locator.entityType == EntityType.MODEL_ENTITIES.value
        and locator.folders[:2] == ["020-Core", "Sales"]
        for locator in deleted
    )
    assert all(model[locator.entityType][locator].is_deleted for locator in deleted)


def test_move_folder_rebases_complete_subtree_and_metadata(model: Model) -> None:
    source_wrappers = model.get_entities_for_locator("folders/020-Core/Sales")
    source_model_names = {
        wrapper.locator.entityName
        for wrapper in source_wrappers
        if wrapper.locator.entityType == EntityType.MODEL_ENTITIES.value
    }

    moved = model.move_entities(
        "folders/020-Core/Sales",
        "folders/020-Core/SalesRenamed",
    )

    moved_folder = next(
        wrapper
        for wrapper in moved
        if wrapper.locator == Locator.from_path("folders/020-Core/SalesRenamed")
    )
    moved_model_names = {
        wrapper.locator.entityName
        for wrapper in moved
        if wrapper.locator.entityType == EntityType.MODEL_ENTITIES.value
    }

    assert moved_folder.entity.name == "SalesRenamed"
    assert moved_folder.entity.path == "020-Core/SalesRenamed"
    assert moved_model_names == source_model_names
    assert all(wrapper.is_deleted for wrapper in source_wrappers)
    assert all(
        wrapper.locator.folders[:2] == ["020-Core", "SalesRenamed"]
        for wrapper in moved
        if wrapper.locator.entityType == EntityType.MODEL_ENTITIES.value
    )


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
