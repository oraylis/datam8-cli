import pytest
from pydantic import ValidationError

from datam8_model import model as m


def test_model_relationship_accepts_internal_target():
    rel = m.ModelRelationship(
        targetLocation=1,
        attributes=[m.ModelAttributeMapping(sourceName="CustomerId", targetName="Id")],
    )

    assert rel.targetLocation == 1
    assert rel.dataSource is None


def test_model_relationship_accepts_external_target():
    rel = m.ModelRelationship(
        dataSource="crm",
        targetLocation="dbo.Customer",
        attributes=[m.ModelAttributeMapping(sourceName="CustomerId", targetName="Id")],
    )

    assert rel.dataSource == "crm"
    assert rel.targetLocation == "dbo.Customer"


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
    ],
)
def test_model_relationship_rejects_mismatched_target_kind(payload):
    with pytest.raises(ValidationError):
        m.ModelRelationship.model_validate(payload)
