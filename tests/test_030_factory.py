import pytest_cases
from test_030_factory_cases import CasesPropertyValueResolution

from datam8 import factory
from datam8.model import Locator, Model, PropertyReference


@pytest_cases.parametrize_with_cases(
    "input", cases=CasesPropertyValueResolution, glob="*_valid"
)
def test_resolve_property(input, model: Model):
    property, value = input[0].split("/")
    ref = PropertyReference(property=property, value=value)

    lookuped_values = sorted(
        factory.resolve_property(model, ref), key=lambda x: x.property
    )
    expected_values = sorted(
        [
            model.propertyValues[Locator.from_path(f"/propertyValues/{ref}")].entity
            for ref in input[1]
        ],
        key=lambda x: x.property,
    )

    assert lookuped_values == expected_values, (
        "Resolved properties do not match expected ones: "
        f"{[x.property for x in expected_values]} but got {[x.property for x in lookuped_values]}"
    )
