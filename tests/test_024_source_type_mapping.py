"""Persisted mappings are authoritative for source type translation."""

import pytest

from datam8.errors import Datam8ValidationError
from datam8.plugins.type_mapping import SourceTypeMapper
from datam8_model.data_source import SourceDataTypeMapping


def mappings(*pairs):
    return [SourceDataTypeMapping(sourceType=source, targetType=target) for source, target in pairs]


@pytest.mark.parametrize(
    "raw,type_pairs,source_pairs,target",
    [
        (" BIGINT ", [("bigint", "long")], [], "long"),
        ("DECIMAL(18,2)", [("decimal", "decimal")], [], "decimal"),
        ("STRUCT<City:STRING>", [("struct", "string")], [], "string"),
        (
            "decimal(18,2)",
            [("decimal", "decimal"), ("DECIMAL(18,2)", "dyndecimal")],
            [],
            "dyndecimal",
        ),
        ("decimal(18,2)", [("decimal(18,2)", "decimal")], [("DECIMAL", "money")], "money"),
        ("BIGINT", [("bigint", "long")], [(" bigint ", "int")], "int"),
    ],
)
def test_mapping_precedence_and_type_syntax(raw, type_pairs, source_pairs, target):
    mapper = SourceTypeMapper(
        mappings(*type_pairs),
        mappings(*source_pairs),
        data_source="crm",
        source_location="customers",
    )
    assert mapper.resolve(raw, column="id") == target


@pytest.mark.parametrize("raw", ["long", "Unknown", ""])
def test_no_implicit_type_or_string_fallback(raw):
    mapper = SourceTypeMapper(
        mappings(("BIGINT", "long")), data_source="crm", source_location="customers"
    )
    with pytest.raises(Datam8ValidationError) as caught:
        mapper.resolve(raw, column="customer_id")
    assert caught.value.details == {
        "dataSource": "crm",
        "sourceLocation": "customers",
        "column": "customer_id",
        "sourceType": raw,
    }


@pytest.mark.parametrize("on_source", [False, True])
def test_duplicate_normalized_keys_are_rejected(on_source):
    duplicates = mappings(("BIGINT", "long"), (" bigint ", "int"))
    with pytest.raises(Datam8ValidationError, match="duplicate"):
        SourceTypeMapper(
            [] if on_source else duplicates,
            duplicates if on_source else [],
            data_source="crm",
            source_location="customers",
        )
