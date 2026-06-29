# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from pathlib import Path
from types import MethodType

import pytest
import pytest_cases
from test_010_model_cases import CasesEntityLookup, CasesLocator, CasesModel

from datam8 import errors
from datam8.model import EntityWrapper, Locator, Model
from datam8.model.model import EntityFileRef
from datam8_model.base import EntityType
from datam8_model.data_product import DataModule, DataProduct
from datam8_model.data_type import DataTypeDefinition
from datam8_model.property import PropertyReference, PropertyValue


@pytest_cases.parametrize_with_cases("attribute", cases=CasesModel, glob="*_attributes")
def test_available_attribute(attribute: str, model: Model):
    assert hasattr(model, attribute), f"Model is missing attribute: {attribute}"


@pytest_cases.parametrize_with_cases("function", cases=CasesModel, glob="*_functions")
def test_available_functions(function: str, model: Model):
    assert hasattr(model, function), f"Model is missing function: {function}"
    assert type(getattr(model, function)) is MethodType


@pytest_cases.parametrize_with_cases("locator", cases=CasesLocator, glob="*_valid")
def test_lookup_entity__valid(locator: str, model: Model):
    """Test the Model.get_entity_by_locator() function with valid locators as an input."""
    entity = model.get_entity_by_locator(locator)

    assert entity.locator == locator, (
        f"Locators do not match - search: {locator} - found: {entity.locator}"
    )
    assert isinstance(entity, EntityWrapper), (
        f"Returned type is not `EntityWrapper` but {type(entity)}"
    )
    assert entity.resolved, "Entity properties have not been resolved."


@pytest_cases.parametrize_with_cases("locator", cases=CasesLocator, glob="*_invalid")
def test_lookup_entity__invalid(locator: str, model: Model):
    """Test the Model().lookup_entity() function with an invalid locator as an input."""

    with pytest.raises(errors.InvalidLocatorError):
        model.get_entity_by_locator(locator)


def test_has_property__raises(model_lazy: Model):
    locator = Locator.from_path("dataProducts/Sales")
    entity = model_lazy.dataProducts[locator]

    with pytest.raises(errors.PropertiesNotResolvedError):
        entity.has_property("test")


@pytest_cases.parametrize_with_cases("test_case", cases=CasesLocator, glob="*_comparison")
def test_locator_comparison(test_case: tuple[str, str, bool]):
    left_side, right_side, expected_result = test_case
    left_side = Locator.from_path(left_side)
    right_side = Locator.from_path(right_side)

    assert (left_side in right_side) == expected_result, (
        "Membership check between `{}` in `{}` had the wrong result: {result}, exptected: {}".format(  # noqa: UP032
            left_side,
            right_side,
            expected_result,
            result=left_side in right_side,
        )
    )


@pytest_cases.parametrize_with_cases("input", cases=CasesEntityLookup, glob="*_dict_valid")
def test_get_entity_dict(input: tuple[str, list[str]], model: Model):
    model.resolve()
    entity_type, entity_names = input

    for entity_name in entity_names:
        match EntityType._value2member_map_[entity_type]:
            case EntityType.DATA_TYPES:
                entity = model.get_data_type(entity_name)
            case EntityType.ATTRIBUTE_TYPES:
                entity = model.get_attribute_type(entity_name)
            case EntityType.ZONES:
                entity = model.get_zone(entity_name)
            case EntityType.PROPERTIES:
                entity = model.get_property(entity_name)
            case EntityType.PROPERTY_VALUES:
                property, name = entity_name.split("/")
                entity = model.get_property_value(name, property)
            case EntityType.DATA_SOURCES:
                entity = model.get_data_source(entity_name)
            case EntityType.DATA_SOURCE_TYPES:
                entity = model.get_data_source_type(entity_name)
            case EntityType.DATA_PRODUCTS:
                entity = model.get_data_product(entity_name)
            case EntityType.DATA_MODULES:
                # NOTE: data modules are currently not being wrapped which results
                # in a different behaviour / class, which needs to be handlered differntly
                data_product, data_module = entity_name.split("/")
                entity = model.get_data_module(data_module, data_product)
                assert isinstance(entity, DataModule), f"Wrong type {type(entity)}"
                return
            case _:
                raise Exception(f"entity type not configured in {__name__}: {entity_type}")

        assert isinstance(entity, EntityWrapper), (
            f"Looked up entity has the wrong type: {type(entity)}"
        )

        expected_locator = f"{entity_type}/{entity_name}"
        assert entity.locator == expected_locator, (
            f"Expected {expected_locator} but got {entity.locator}"
        )


def test_get_entities(model: Model):
    entities = model.get_entities("/modelEntities")

    assert len(entities) > 0


def test_move_folder_updates_folder_metadata(model: Model):
    moved = model.move_entities("folders/020-Core/Sales", "folders/020-Core/SalesRenamed")
    moved_folder = next(
        (
            wrapper
            for wrapper in moved
            if wrapper.locator.entityType == EntityType.FOLDERS.value
            and wrapper.locator.entityName == "SalesRenamed"
        ),
        None,
    )

    assert moved_folder is not None
    assert moved_folder.entity.name == "SalesRenamed"
    assert moved_folder.entity.path == "020-Core/SalesRenamed"


def test_resolve_wrapper_keeps_local_properties_unmodified():
    local_ref = PropertyReference(property="localProp", value="localValue")
    inherited_ref = PropertyReference(property="inheritedProp", value="inheritedValue")
    wrapper = EntityWrapper(
        locator=Locator.from_path("dataProducts/Sales"),
        source_file=Path("Base/DataProducts.json"),
        entity=DataProduct(
            name="Sales",
            properties=[local_ref],
            dataModules=[DataModule(name="Module1")],
        ),
    )
    captured: dict[str, list[PropertyReference]] = {}

    class DummyResolver:
        def get_inherited_property_references(self, current_wrapper):
            assert current_wrapper is wrapper
            return [inherited_ref]

        def _resolve_properties(self, current_wrapper, props):
            assert current_wrapper is wrapper
            captured["props"] = list(props)

        def _resolve_model_attributes(self, current_wrapper):
            assert current_wrapper is wrapper

    resolver = DummyResolver()
    before_local = list(wrapper.entity.properties or [])
    resolved = Model.resolve_wrapper(resolver, wrapper)
    after_local = list(resolved.entity.properties or [])

    assert resolved.resolved
    assert after_local == before_local
    assert local_ref in captured["props"]
    assert inherited_ref in captured["props"]


def _model_entity_payload_template(model: Model) -> tuple[dict, str]:
    wrapper = next(iter(model.modelEntities.values()))
    payload = wrapper.entity.model_copy().model_dump(mode="json")
    payload["id"] = 999999
    payload["name"] = "ClientProvidedName"
    zone_folder = wrapper.locator.folders[0]
    return payload, zone_folder


def test_add_model_entity_uses_next_id_after_existing_max(model: Model):
    existing_max = max(wrapper.entity.id for wrapper in model.modelEntities.values())
    payload, zone_folder = _model_entity_payload_template(model)

    created = model.add_entity(f"modelEntities/{zone_folder}/IdSequenceRegression", payload)

    assert created.entity.id == existing_max + 1


def test_add_model_entity_ignores_client_supplied_id(model: Model):
    existing_max = max(wrapper.entity.id for wrapper in model.modelEntities.values())
    payload, zone_folder = _model_entity_payload_template(model)
    payload["id"] = 1

    created = model.add_entity(f"modelEntities/{zone_folder}/ClientIdIgnored", payload)

    assert created.entity.id == existing_max + 1
    assert created.entity.id != 1


def test_add_model_entity_uses_dedicated_model_file_path(model: Model):
    existing = next(iter(model.modelEntities.values()))
    payload, zone_folder = _model_entity_payload_template(model)
    entity_name = "SourceFileRegression"

    created = model.add_entity(f"modelEntities/{zone_folder}/{entity_name}", payload)
    expected = (
        model.get_base_path_for_entity_type(EntityType.MODEL_ENTITIES)
        / zone_folder
        / f"{entity_name}.json"
    )

    assert created.source_file == expected
    assert created.source_file != existing.source_file


def test_entity_file_ref_delete_property_values_uses_property_and_name(tmp_path: Path):
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

    color_locator = Locator.from_path("/propertyValues/Color/Default")
    status_locator = Locator.from_path("/propertyValues/Status/Default")
    file_ref = EntityFileRef(
        _type=EntityType.PROPERTY_VALUES,
        file_path=file_path,
        locators=[color_locator, status_locator],
    )
    wrapper = EntityWrapper(
        locator=color_locator,
        source_file=file_path,
        entity=PropertyValue(name="Default", property="Color"),
    )

    was_file_deleted = file_ref.delete(wrappers=[wrapper])

    assert was_file_deleted is False
    assert file_path.exists()
    assert file_ref.locators == [status_locator]

    content = file_path.read_text(encoding="utf-8")
    assert '"property": "Color"' not in content
    assert '"property": "Status"' in content


def test_entity_file_ref_update_property_values_uses_property_and_name(tmp_path: Path):
    file_path = tmp_path / "PropertyValues.json"
    file_path.write_text(
        """{
  "type": "propertyValues",
  "propertyValues": [
    { "name": "daily", "property": "schedules", "displayName": "Daily" },
    { "name": "sales_daily", "property": "jobs", "displayName": "Sales (Daily)" }
  ]
}
""",
        encoding="utf-8",
    )

    schedules_daily = Locator.from_path("/propertyValues/schedules/daily")
    jobs_sales_daily = Locator.from_path("/propertyValues/jobs/sales_daily")
    file_ref = EntityFileRef(
        _type=EntityType.PROPERTY_VALUES,
        file_path=file_path,
        locators=[schedules_daily, jobs_sales_daily],
    )

    wrapper = EntityWrapper(
        locator=Locator.from_path("/propertyValues/jobs/daily"),
        source_file=file_path,
        entity=PropertyValue(name="daily", property="jobs", displayName="Sales (Daily)"),
    )

    file_ref.update(wrappers=[wrapper])

    content = file_path.read_text(encoding="utf-8")
    assert '"name": "daily",' in content
    assert '"property": "schedules"' in content
    assert '"property": "jobs"' in content
    assert '"name": "sales_daily"' in content


def test_entity_file_ref_update_renamed_base_entity_replaces_old_key(tmp_path: Path):
    file_path = tmp_path / "DataTypes.json"
    file_path.write_text(
        """{
  "type": "dataTypes",
  "dataTypes": [
    { "name": "Text", "displayName": "Text", "targets": { "databricks": "string" } },
    { "name": "Number", "displayName": "Number", "targets": { "databricks": "int" } }
  ]
}
""",
        encoding="utf-8",
    )

    old_locator = Locator.from_path("/dataTypes/Text")
    new_locator = Locator.from_path("/dataTypes/String")
    file_ref = EntityFileRef(
        _type=EntityType.DATA_TYPES,
        file_path=file_path,
        locators=[new_locator, Locator.from_path("/dataTypes/Number")],
    )
    file_ref.renamed_locators[old_locator] = new_locator
    wrapper = EntityWrapper(
        locator=new_locator,
        source_file=file_path,
        entity=DataTypeDefinition(
            name="String",
            displayName="String",
            targets={"databricks": "string"},
        ),
    )

    file_ref.update(wrappers=[wrapper])

    content = file_path.read_text(encoding="utf-8")
    assert '"name": "Text"' not in content
    assert '"name": "String"' in content
    assert '"name": "Number"' in content


def test_entity_file_ref_update_renamed_property_value_replaces_old_compound_key(tmp_path: Path):
    file_path = tmp_path / "PropertyValues.json"
    file_path.write_text(
        """{
  "type": "propertyValues",
  "propertyValues": [
    { "name": "daily", "property": "schedules", "displayName": "Daily" },
    { "name": "daily", "property": "jobs", "displayName": "Daily Job" }
  ]
}
""",
        encoding="utf-8",
    )

    old_locator = Locator.from_path("/propertyValues/schedules/daily")
    new_locator = Locator.from_path("/propertyValues/jobs/weekly")
    file_ref = EntityFileRef(
        _type=EntityType.PROPERTY_VALUES,
        file_path=file_path,
        locators=[new_locator, Locator.from_path("/propertyValues/jobs/daily")],
    )
    file_ref.renamed_locators[old_locator] = new_locator
    wrapper = EntityWrapper(
        locator=new_locator,
        source_file=file_path,
        entity=PropertyValue(name="weekly", property="jobs", displayName="Weekly Job"),
    )

    file_ref.update(wrappers=[wrapper])

    content = file_path.read_text(encoding="utf-8")
    assert '"property": "schedules"' not in content
    assert '"name": "weekly"' in content
    assert '"displayName": "Weekly Job"' in content
    assert '"displayName": "Daily Job"' in content


# @parametrize_with_cases("locator", cases=CasesLocator, glob="*_multiple")
# def test_lookup_entity__multiple(locator, model):
#     """Test Model.lookup_entity() with multiple resolve locators."""
#
#     with pytest.raises(MultipleLocatorsFoundException):
#         # TODO: current generator does not do fuzzzy or regex matching
#         raise MultipleLocatorsFoundException("dummy")
#
#
# @parametrize_with_cases("locator", cases=CasesLocator, glob="*_unkown")
# def test_lookup_entity__unkown(locator, model):
#     """Test Model.lookup_entity() with unkownk locator."""
#
#     with pytest.raises(LocatorNotFoundException):
#         model.lookup_entity(locator)
