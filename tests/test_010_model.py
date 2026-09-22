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

from types import MethodType

import pytest
import pytest_cases
from test_010_model_cases import CasesEntityLookup, CasesLocator, CasesModel

from datam8 import errors
from datam8.model import EntityWrapper, Locator, Model
from datam8_model.base import EntityType
from datam8_model.data_product import DataModule


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


@pytest_cases.parametrize_with_cases("test_case", cases=CasesLocator, glob="*_comparison")
def test_locator_comparison(test_case: tuple[str, str, bool]):
    left_side, right_side, expected_result = test_case
    left_side = Locator.from_path(left_side)
    right_side = Locator.from_path(right_side)

    assert (left_side in right_side) == expected_result, (
        "Membership check between `{}` in `{}` had the wrong result: {result}, expected: {}".format(  # noqa: UP032
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
            case EntityType.DATA_MODULES:
                # NOTE: data modules are currently not being wrapped which results
                # in a different behaviour / class, which needs to be handlered differently
                data_product, data_module = entity_name.split("/")
                entity = model.get_data_module(data_module, data_product)
                assert isinstance(entity, DataModule), f"Wrong type {type(entity)}"
                return
            case _:
                entity = model[entity_type].get(entity_name)

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


def test_move_entities(model: Model, monkeypatch: pytest.MonkeyPatch):
    # Keep the shared solution fixture untouched. This test verifies the model
    # move itself; moving function source files is covered by the function API.
    monkeypatch.setattr(
        "datam8.model.model.functions.move_functions",
        lambda *args, **kwargs: None,
    )

    wrapper = next(model.modelEntities.values())
    new_locator = Locator(
        entityType=wrapper.locator.entityType,
        folders=wrapper.locator.folders,
        entityName=f"{wrapper.locator.entityName}_moved",
    )
    moved = model.move_entities(wrapper.locator, new_locator)

    assert len(moved) == 1
    assert model.modelEntities.get(new_locator)


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
