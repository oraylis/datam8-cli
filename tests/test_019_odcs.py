from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from pytest_cases import parametrize_with_cases
from test_019_odcs_cases import CasesOdcsTypes, contract

from datam8.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.plugins.builtins.odcs import OdcsFile
from datam8.plugins.type_mapping import SourceTypeMapper
from datam8_model.attribute import Attribute
from datam8_model.data_type import DataType
from datam8_model.model import ModelEntity
from datam8_model.plugin import Capability


def write_contract(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data) if path.suffix.lower() == ".json" else yaml.safe_dump(data)
    path.write_text(text, encoding="utf-8")
    return path


def enrich_entity(metadata):
    entity = ModelEntity(
        name="temp",
        id=1,
        attributes=[
            Attribute(
                name=field.name,
                ordinalNumber=field.ordinal,
                attributeType="Default",
                dataType=DataType(type="string", nullable=True),
                dateAdded=datetime.now(UTC),
            )
            for field in metadata.iter_source_fields()
        ],
        sources=[],
        transformations=[],
        relationships=[],
    )
    metadata.apply_import_metadata(entity)
    return entity


@parametrize_with_cases("prop,target", cases=CasesOdcsTypes)
def test_type_mapping(prop, target, tmp_path, builtin_plugin):
    path = write_contract(tmp_path / "contract.yaml", contract([prop]))
    plugin = builtin_plugin(OdcsFile, {"path": str(path)})
    metadata = plugin.get_table_metadata("contract.yaml#customers")
    field = next(metadata.iter_source_fields())
    mapper = SourceTypeMapper(
        plugin.get_data_type_mappings(),
        data_source="Contracts",
        source_location="contract.yaml#customers",
    )
    if target is None:
        with pytest.raises(Datam8ValidationError, match="VendorType"):
            mapper.resolve(field.dataType, column=field.name)
    else:
        assert mapper.resolve(field.dataType, column=field.name) == target
    assert field.dataType == prop.get("physicalType", prop.get("logicalType"))
    assert field.ordinal == 1 and field.isNullable


@pytest.mark.parametrize("extension", [".yaml", ".yml", ".json", ".JSON"])
def test_file_and_directory_navigation(extension, tmp_path, builtin_plugin):
    path = write_contract(tmp_path / "contracts" / ("orders #1" + extension), contract())
    data = contract()
    data["schema"].append(
        {"name": "with / # ü", "properties": [{"name": "a", "logicalType": "string"}]}
    )
    write_contract(path, data)
    single = builtin_plugin(OdcsFile, {"path": str(path)})
    directory = builtin_plugin(OdcsFile, {"path": "contracts"})
    assert directory.test_connection() is None
    assert single.test_connection() is None
    assert not single.is_capable_of(Capability.PREVIEW_DATA)
    for _ in range(2):
        entry = directory.list_source().to_dicts()[0]
        assert entry["type"] == "CONTAINER"
        objects = directory.list_source(entry["sourceLocation"]).to_dicts()
        assert objects == single.list_source().to_dicts()
        location = objects[1]["sourceLocation"]
        assert location.endswith("#" + quote("with / # ü", safe=""))
        assert directory.get_table_metadata(location).source_object.name == "with / # ü"
        assert single.get_table_metadata(location).dataframe.height == 1
    assert single.extended_properties["path"] == str(path)


def test_subdirectory_and_empty_navigation(tmp_path, builtin_plugin):
    (tmp_path / "contracts" / "nested").mkdir(parents=True)
    (tmp_path / "contracts" / "readme.txt").write_text("not a contract")
    plugin = builtin_plugin(OdcsFile, {"path": "contracts"})
    assert plugin.list_source()["type"].to_list() == ["DIRECTORY"]
    assert plugin.list_source("nested").height == 0
    assert "sourceLocation" in plugin.list_source("nested").columns


def test_metadata_fields(tmp_path, builtin_plugin):
    data = contract(
        [
            {
                "name": "id",
                "physicalName": "customer_id",
                "businessName": "Kundennummer",
                "description": "Primary key",
                "logicalType": "integer",
                "physicalType": "BIGINT",
                "required": True,
                "primaryKey": True,
            },
            {"name": "amount", "logicalType": "number", "physicalType": "DECIMAL(10,0)"},
            {
                "name": "label",
                "logicalType": "string",
                "physicalType": "VARCHAR(80)",
                "logicalTypeOptions": {"maxLength": 42},
            },
            {"name": "fallback_length", "physicalType": "CHAR(12)"},
        ]
    )
    data["schema"][0].update(
        physicalName="crm_customers", businessName="Kunden", description="Customer master"
    )
    path = write_contract(tmp_path / "test.json", data)
    metadata = builtin_plugin(OdcsFile, {"path": str(path)}).get_table_metadata(
        "test.json#customers"
    )
    assert metadata.source_object.name == "crm_customers"
    assert metadata.source_object.description == "Customer master"
    fields = list(metadata.iter_source_fields())
    entity = enrich_entity(metadata)
    assert entity.name == "crm_customers"
    assert entity.displayName == "Kunden"
    assert entity.attributes[0].displayName == "Kundennummer"
    assert fields[0].name == "customer_id"
    assert not fields[0].isNullable and fields[0].isPrimaryKey
    assert fields[0].description == "Primary key"
    assert fields[1].numericPrecision == 10 and fields[1].numbericScale == 0
    assert fields[2].maxLength == 42 and fields[3].maxLength == 12
    assert entity.attributes[1].displayName is None


@pytest.mark.parametrize("version", ["v3.1.0", "v3.2.1", "3.2.0"])
def test_other_versions_rejected(version, tmp_path, builtin_plugin):
    path = write_contract(tmp_path / "test.json", contract(apiVersion=version))
    with pytest.raises(Datam8ValidationError, match="apiVersion"):
        builtin_plugin(OdcsFile, {"path": str(path)}).test_connection()


@pytest.mark.parametrize(
    "data,pattern",
    [
        (contract(kind="Other"), "kind"),
        (contract(schema=[{"name": "x"}, {"name": "x"}]), "duplicate schema"),
        (contract([{"name": "a"}]), "physicalType or logicalType"),
        (contract(schema=[{"name": "customers", "properties": []}]), "no importable columns"),
        (
            contract(
                [{"name": "a", "logicalType": "string"}, {"name": "a", "logicalType": "string"}]
            ),
            "duplicate or empty column",
        ),
        (
            contract(
                [{"name": "a", "logicalType": "string", "logicalTypeOptions": {"maxLength": 0}}]
            ),
            "positive length",
        ),
        (contract([{"name": "${FIELD}", "logicalType": "integer"}]), "unresolved variable"),
        (
            contract([{"name": "a", "logicalType": "integer", "physicalType": "${TYPE}"}]),
            "unresolved variable",
        ),
    ],
)
def test_invalid_import(data, pattern, tmp_path, builtin_plugin):
    path = write_contract(tmp_path / "test.json", data)
    with pytest.raises(Datam8ValidationError, match=pattern):
        builtin_plugin(OdcsFile, {"path": str(path)}).get_table_metadata("test.json#customers")


@pytest.mark.parametrize(
    "text", ["[1, 2]", "name: a\nname: b\n", "a: [", "!!python/object:builtins.object {}"]
)
def test_invalid_or_unsafe_yaml(text, tmp_path, builtin_plugin):
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(Datam8ValidationError):
        builtin_plugin(OdcsFile, {"path": str(path)}).test_connection()


def test_dates_and_unused_variables(tmp_path, builtin_plugin):
    path = tmp_path / "test.yaml"
    path.write_text(
        yaml.safe_dump(contract())
        + "contractCreatedTs: 2026-10-02T10:00:00Z\ndescription:\n  purpose: ${PURPOSE}\n"
    )
    assert builtin_plugin(OdcsFile, {"path": str(path)}).test_connection() is None


@pytest.mark.parametrize(
    "location",
    [
        "../outside.json#customers",
        "%2E%2E/outside.json#customers",
        "C:/outside.json#customers",
        "/outside.json#customers",
    ],
)
def test_path_escape(location, tmp_path, builtin_plugin):
    (tmp_path / "contracts").mkdir()
    with pytest.raises(Datam8ValidationError, match="root"):
        builtin_plugin(OdcsFile, {"path": "contracts"}).get_table_metadata(location)


def test_single_file_boundary_and_missing_files(tmp_path, builtin_plugin):
    path = write_contract(tmp_path / "test.json", contract())
    write_contract(tmp_path / "other.json", contract())
    plugin = builtin_plugin(OdcsFile, {"path": str(path)})
    with pytest.raises(Datam8ValidationError, match="root"):
        plugin.get_table_metadata("other.json#customers")
    with pytest.raises(Datam8NotFoundError, match="no schema"):
        plugin.get_table_metadata("test.json#missing")
    with pytest.raises(Datam8NotFoundError, match="does not exist"):
        builtin_plugin(OdcsFile, {"path": "missing.json"}).test_connection()
    with pytest.raises(Datam8ValidationError, match="protocol"):
        builtin_plugin(OdcsFile, {"path": str(path), "protocol": "https"}).test_connection()


def test_symlink_escape(tmp_path, builtin_plugin):
    root = tmp_path / "contracts"
    root.mkdir()
    outside = write_contract(tmp_path / "outside.json", contract())
    try:
        (root / "escape.json").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks require Developer Mode or elevated Windows privileges")
    plugin = builtin_plugin(OdcsFile, {"path": str(root)})
    assert plugin.list_source().height == 0
    with pytest.raises(Datam8ValidationError, match="root"):
        plugin.get_table_metadata("escape.json#customers")


def test_official_full_example(builtin_plugin):
    # Unmodified Apache-2.0 example from the pinned upstream v3.2.0 release:
    # docs/examples/all/full-example.odcs.yaml (license shipped with the schema).
    path = Path(__file__).parent / "builtin_plugins/full-example.odcs.yaml"
    plugin = builtin_plugin(OdcsFile, {"path": str(path.resolve())})
    assert plugin.test_connection() is None
    locations = plugin.list_source().to_dicts()
    assert len(locations) == 2
    first = plugin.get_table_metadata(locations[0]["sourceLocation"])
    second = plugin.get_table_metadata(locations[1]["sourceLocation"])
    assert first.source_object.name == "tbl_1"
    entity = enrich_entity(first)
    assert entity.displayName == "Core Payment Metrics"
    assert [field.name for field in first.iter_source_fields()] == [
        "txn_ref_dt",
        "rcvr_id",
        "rcvr_cntry_code",
    ]
    entity = enrich_entity(second)
    assert entity.displayName == "Receivers Master Data"
    fields = list(second.iter_source_fields())
    assert fields[2].maxLength == 255
    assert (
        fields[-1].name == "receiver_attributes"
        and SourceTypeMapper(
            plugin.get_data_type_mappings(),
            data_source="Contracts",
            source_location=locations[1]["sourceLocation"],
        ).resolve(fields[-1].dataType, column=fields[-1].name)
        == "string"
    )
