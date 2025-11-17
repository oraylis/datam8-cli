from types import MethodType

import pytest
import pytest_cases
from test_010_model_cases import CasesEntityLookup, CasesLocator, CasesModel

from dm8gen import model_exceptions as errors
from dm8gen.model import EntityWrapper, Locator, Model
from dm8model.base import EntityType
from dm8model.data_product import DataModule


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


@pytest_cases.parametrize_with_cases(
    "input", cases=CasesEntityLookup, glob="*_dict_valid"
)
def test_get_entity_dict(input: tuple[str, list[str]], model: Model):
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
                entity = model.get_property_value(property, name)
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
                entity = model.get_data_module(data_product, data_module)
                assert isinstance(entity, DataModule), f"Wrong type {type(entity)}"
                return
            case _:
                raise Exception(
                    f"entity type not configured in {__name__}: {entity_type}"
                )

        assert isinstance(entity, EntityWrapper), (
            f"Looked up entity has the wrong type: {type(entity)}"
        )

        expected_locator = f"{entity_type}/{entity_name}"
        assert entity.locator == expected_locator, (
            f"Expected {expected_locator} but got {entity.locator}"
        )


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
