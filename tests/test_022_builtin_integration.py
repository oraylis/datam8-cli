from __future__ import annotations

import json

import pytest
from builtin_plugins.solution import create_solution
from fastapi.testclient import TestClient
from test_019_odcs import write_contract
from test_019_odcs_cases import contract
from typer.testing import CliRunner

from datam8 import config, factory, source
from datam8.api.app import create_app
from datam8.app import app
from datam8.errors import Datam8ValidationError
from datam8.plugins.builtins.databricks_uc import DatabricksUnityCatalog
from datam8.plugins.builtins.file import CsvFile
from datam8.plugins.builtins.odcs import OdcsFile
from datam8.plugins.manager import PluginManager
from datam8_model.data_source import SourceDataTypeMapping


@pytest.mark.parametrize("cls", [CsvFile, OdcsFile, DatabricksUnityCatalog])
def test_registry_aliases_and_ui_schema(cls):
    manager = PluginManager()
    canonical = cls.manifest().id
    for identifier in (canonical, canonical.removeprefix("builtin:")):
        assert manager.get_plugin_manifest(identifier) == cls.manifest()
        assert manager.get_plugin(identifier) is cls
    assert manager.get_plugins().count(cls.manifest()) == 1
    assert cls.get_ui_schema().authModes


def test_odcs_api_import_save_reload_and_refresh(tmp_path, builtin_environment):
    data = contract(
        [
            {
                "name": "id",
                "businessName": "Kundennummer",
                "logicalType": "integer",
                "physicalType": "VendorInteger",
                "required": True,
                "primaryKey": True,
            },
            {"name": "amount", "logicalType": "number", "physicalType": "DECIMAL(10,0)"},
            {"name": "preferences", "logicalType": "array", "items": {"logicalType": "string"}},
        ]
    )
    data["schema"][0].update(
        physicalName="crm_customers", businessName="Kunden", description="Customer master"
    )
    write_contract(tmp_path / "contract.yaml", data)
    path = create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.yaml"})])
    sources_file = tmp_path / "Base/DataSources.json"
    sources_config = json.loads(sources_file.read_text())
    sources_config["dataSources"][0]["dataTypeMapping"] = [
        {"sourceType": "VendorInteger", "targetType": "long"}
    ]
    sources_file.write_text(json.dumps(sources_config), encoding="utf-8")
    config.set_solution(path)
    factory._model = factory.create_model()
    with TestClient(create_app()) as client:
        response = client.get("/plugins/builtin:OdcsFile/ui-schema")
        assert response.status_code == 200, response.text
        assert client.get("/sources/Contracts/test").status_code == 200
        locations = client.get("/sources/Contracts/locations").json()["items"]
        location = locations[0]["sourceLocation"]
        metadata = client.get(
            "/sources/Contracts/locations/metadata", params={"source_location": location}
        )
        assert metadata.status_code == 200, metadata.text
        field_metadata = metadata.json()["items"][0]
        assert field_metadata["dataType"] == "VendorInteger"
        assert "displayName" not in field_metadata
        assert "targetDataType" not in field_metadata
        assert metadata.json()["object"]["name"] == "crm_customers"
        assert metadata.json()["sourceLocation"] == location
        description = client.get(
            "/sources/Contracts/locations/import-description", params={"source_location": location}
        )
        assert description.status_code == 200, description.text
        imported = description.json()["entity"]
        assert imported["name"] == "crm_customers" and imported["displayName"] == "Kunden"
        assert imported["attributes"][0]["displayName"] == "Kundennummer"
        assert [attr["dataType"]["type"] for attr in imported["attributes"]] == [
            "long",
            "decimal",
            "string",
        ]
        assert imported["attributes"][1]["dataType"]["scale"] == 0
        assert imported["sources"][0]["sourceLocation"] == location
        assert imported["sources"][0]["metadataLocation"] == location
        assert imported["sources"][0]["mapping"][0]["sourceDataType"]["type"] == "VendorInteger"
        assert (
            client.get(
                "/sources/Contracts/locations/preview", params={"source_location": location}
            ).status_code
            == 400
        )
        response = client.put(
            "/sources/Contracts/import",
            json={
                "locator": "modelEntities/Stage/Customers",
                "sourceLocation": location,
            },
        )
        assert response.status_code == 200, response.text
        saved = json.loads((tmp_path / "Model/Stage/Customers.json").read_text())
        assert saved["name"] == "Customers" and saved["displayName"] == "Kunden"
        assert saved["attributes"][0]["displayName"] == "Kundennummer"
        assert saved["attributes"][0]["dataType"]["type"] == "long"
        assert saved["sources"][0]["mapping"][0]["sourceDataType"]["type"] == "VendorInteger"
        assert saved["attributes"][1]["dataType"]["scale"] == 0
        assert saved["attributes"][2]["dataType"]["type"] == "string"
        assert client.post("/model/reload", params={"force": True}).status_code == 200
        unchanged = client.get(
            "/sources/compare", params={"locator": "modelEntities/Stage/Customers"}
        )
        assert unchanged.status_code == 200, unchanged.text
        assert not unchanged.json()["has_changes"]
        data["schema"][0]["properties"].append(
            {"name": "added", "businessName": "Neu", "logicalType": "string"}
        )
        write_contract(tmp_path / "contract.yaml", data)
        refreshed = client.get(
            "/sources/compare", params={"locator": "modelEntities/Stage/Customers"}
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["wrapper"]["entity"]["attributes"][-1]["displayName"] == "Neu"
        sources_config["dataSources"][0]["dataTypeMapping"][0]["targetType"] = "int"
        sources_file.write_text(json.dumps(sources_config), encoding="utf-8")
        assert client.post("/model/reload", params={"force": True}).status_code == 200
        complete = client.get(
            "/sources/compare", params={"locator": "modelEntities/Stage/Customers"}
        )
        assert complete.status_code == 200, complete.text
        entity = complete.json()["wrapper"]["entity"]
        assert entity["attributes"][0]["dataType"]["type"] == "int"
        assert entity["sources"][0]["mapping"][0]["sourceDataType"]["type"] == "VendorInteger"
        sources_only = client.get(
            "/sources/compare",
            params={"locator": "modelEntities/Stage/Customers", "mode": "sources-only"},
        )
        assert sources_only.status_code == 200, sources_only.text
        assert (
            sources_only.json()["wrapper"]["entity"]["attributes"][0]["dataType"]["type"] == "long"
        )
        patched = client.patch("/entities/modelEntities/Stage/Customers", json=entity)
        assert patched.status_code == 200, patched.text
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload", params={"force": True}).status_code == 200
        assert (
            json.loads((tmp_path / "Model/Stage/Customers.json").read_text())["attributes"][0][
                "dataType"
            ]["type"]
            == "int"
        )
        unchanged = client.get(
            "/sources/compare", params={"locator": "modelEntities/Stage/Customers"}
        )
        assert unchanged.status_code == 200 and not unchanged.json()["has_changes"]


def test_odcs_directory_api_navigation_and_legacy_csv_description(tmp_path, builtin_environment):
    data = contract()
    data["schema"][0].update(name="customer / ü", physicalName="crm_customers")
    write_contract(tmp_path / "contracts/nested/orders #1.yaml", data)
    (tmp_path / "csv").mkdir()
    (tmp_path / "csv/customers.csv").write_text("id,name\n1,Alice\n", encoding="utf-8")
    config.set_solution(
        create_solution(
            tmp_path,
            [
                (OdcsFile, "Contracts", {"path": "contracts"}),
                (CsvFile, "Csv", {"path": str(tmp_path / "csv"), "protocol": "file"}),
            ],
        )
    )
    factory._model = factory.create_model()
    with TestClient(create_app()) as client:
        directory = client.get("/sources/Contracts/locations").json()["items"][0]
        assert directory["type"] == "DIRECTORY"
        container = client.get(
            "/sources/Contracts/locations", params={"source_location": directory["sourceLocation"]}
        ).json()["items"][0]
        assert container["type"] == "CONTAINER"
        leaf = client.get(
            "/sources/Contracts/locations", params={"source_location": container["sourceLocation"]}
        ).json()["items"][0]
        assert leaf["name"] == "crm_customers"
        assert leaf["sourceLocation"] == "nested/orders%20%231.yaml#customer%20%2F%20%C3%BC"
        assert (
            client.get(
                "/sources/Contracts/locations/import-description",
                params={"source_location": leaf["sourceLocation"]},
            ).json()["entity"]["name"]
            == "crm_customers"
        )
        listed = client.get("/sources/Csv/locations")
        assert listed.status_code == 200, listed.text
        csv = listed.json()["items"][0]
        assert csv["type"] == "FILE"
        description = client.get(
            "/sources/Csv/locations/import-description", params={"source_location": csv["object"]}
        )
        assert description.status_code == 200, description.text
        assert description.json() == {"entity": None}


@pytest.mark.parametrize("mode", ["pat", "oauthClientCredentials", "azureServicePrincipal"])
def test_uc_builtin_api_import_save_reload_refresh(
    mode, tmp_path, make_plugin, workspace, monkeypatch
):
    plugin = make_plugin(mode)
    props = dict(plugin._data_source.extendedProperties)
    path = create_solution(tmp_path, [(DatabricksUnityCatalog, "UC", props)])
    config.set_solution(path)
    monkeypatch.setattr(
        DatabricksUnityCatalog,
        "_entra_token_url",
        lambda self, tenant: workspace.url + f"/{tenant}/oauth2/v2.0/token",
    )
    factory._model = factory.create_model()
    with TestClient(create_app()) as client:
        assert client.get("/sources/UC/test").status_code == 200
        description = client.get(
            "/sources/UC/locations/import-description",
            params={"source_location": "[main.sales].[Customers]"},
        )
        assert description.status_code == 200, description.text
        described = description.json()["entity"]
        assert described["name"] == "Customers"
        assert described["sources"][0]["sourceLocation"] == "`main`.`sales`.`Customers`"
        assert described["sources"][0]["metadataLocation"] is None
        response = client.put(
            "/sources/UC/import",
            json={
                "locator": "modelEntities/Stage/Customers",
                "sourceLocation": "[main.sales].[Customers]",
            },
        )
        assert response.status_code == 200, response.text
        saved = json.loads((tmp_path / "Model/Stage/Customers.json").read_text())
        assert saved["sources"][0]["sourceLocation"] == "`main`.`sales`.`Customers`"
        assert "metadataLocation" not in saved["sources"][0]
        assert [a["dataType"]["type"] for a in saved["attributes"]] == [
            "long",
            "string",
            "decimal",
            "bit",
            "string",
        ]
        assert saved["attributes"][2]["dataType"]["scale"] == 0
        assert saved["sources"][0]["mapping"][4]["sourceDataType"]["type"] == "struct<city:string>"
        assert client.post("/model/reload", params={"force": True}).status_code == 200
        for refresh_mode in ("complete", "sources-only"):
            unchanged = client.get(
                "/sources/compare",
                params={"locator": "modelEntities/Stage/Customers", "mode": refresh_mode},
            )
            assert unchanged.status_code == 200, unchanged.text
            assert not unchanged.json()["has_changes"]
            refreshed_source = unchanged.json()["wrapper"]["entity"]["sources"][0]
            assert refreshed_source["sourceLocation"] == "`main`.`sales`.`Customers`"
            assert refreshed_source["metadataLocation"] is None
        assert (
            client.get(
                "/sources/UC/locations/preview",
                params={"source_location": "[main.sales].[Customers]", "limit": 2},
            ).status_code
            == 200
        )
        workspace.columns.append(
            {"name": "added", "type_name": "INT", "position": 5, "nullable": True}
        )
        for _ in range(2):
            compared = client.get(
                "/sources/compare", params={"locator": "modelEntities/Stage/Customers"}
            )
            assert compared.status_code == 200, compared.text
            assert any(
                a["name"] == "added" for a in compared.json()["wrapper"]["entity"]["attributes"]
            )
            patched = client.patch(
                "/entities/modelEntities/Stage/Customers", json=compared.json()["wrapper"]["entity"]
            )
            assert patched.status_code == 200, patched.text
            assert client.post("/model/save").status_code == 204
            assert client.post("/model/reload", params={"force": True}).status_code == 200
        assert not list((tmp_path / "Plugins").iterdir())


@pytest.mark.parametrize("cls", [OdcsFile, DatabricksUnityCatalog])
def test_cli_navigation_and_import(cls, tmp_path, builtin_plugin, make_plugin):
    if cls is OdcsFile:
        write_contract(tmp_path / "contract.json", contract())
        properties = {"path": "contract.json"}
        location = "contract.json#customers"
    else:
        properties = dict(make_plugin()._data_source.extendedProperties)
        location = "main.sales.Customers"
    path = create_solution(tmp_path, [(cls, "Source", properties)])
    runner = CliRunner()
    for args in (
        ["sources", "list", "Source"],
        ["sources", "metadata", "Source", location],
        ["sources", "import", "Source", location, "modelEntities/Stage/Imported"],
    ):
        result = runner.invoke(app, [*args, "-s", str(path)])
        assert result.exit_code == 0, f"{result.output}\n{result.exception}"
    saved = json.loads((tmp_path / "Model/Stage/Imported.json").read_text())
    if cls is DatabricksUnityCatalog:
        assert saved["sources"][0]["sourceLocation"] == "`main`.`sales`.`Customers`"
        assert "metadataLocation" not in saved["sources"][0]


def test_optional_metadata_preserves_existing_plugin_imports(
    tmp_path, builtin_environment, monkeypatch
):
    """Legacy plugins retain metadata shape but cannot override persisted mappings."""
    from types import SimpleNamespace

    import polars as pl

    from datam8.plugins.base import TableMetadata
    from datam8_model.data_source import SourceObject

    metadata = TableMetadata(
        pl.DataFrame([{"name": "a", "ordinal": 1, "dataType": "legacy"}]),
        SourceObject(name="table", type="TABLE"),
    )
    plugin = SimpleNamespace(
        get_table_metadata=lambda _: metadata,
        resolve_source_type=lambda _: pytest.fail("Plugin resolver must not be called"),
        get_sources=lambda _: None,
    )
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *args, **kwargs: plugin)
    model = SimpleNamespace(
        dataSources={
            "Source": SimpleNamespace(entity=SimpleNamespace(type="Test", dataTypeMapping=None))
        },
        dataSourceTypes={
            "Test": SimpleNamespace(
                entity=SimpleNamespace(
                    dataTypeMapping=[
                        SourceDataTypeMapping(sourceType="legacy", targetType="string")
                    ]
                )
            )
        },
        attributeTypes=SimpleNamespace(
            get_many_where=lambda _: [SimpleNamespace(entity=SimpleNamespace(name="Default"))]
        ),
    )
    entity = source.read_from_data_source("Source", "table", model=model)
    assert entity.attributes[0].dataType.type == "string"
    assert entity.attributes[0].displayName is None and entity.displayName is None


def test_odcs_configured_mappings_override_logical_hints(tmp_path, builtin_environment):
    write_contract(
        tmp_path / "contract.yaml",
        contract(
            [
                {
                    "name": "id",
                    "physicalType": "VendorType",
                    "logicalType": "integer",
                    "logicalTypeOptions": {"format": "i16"},
                },
                {"name": "label", "physicalType": "VendorType", "logicalType": "string"},
                {"name": "payload", "physicalType": "BIGINT", "logicalType": "object"},
            ]
        ),
    )
    config.set_solution(
        create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.yaml"})])
    )
    model = factory.create_model()
    with pytest.raises(Datam8ValidationError, match="VendorType"):
        source.read_from_data_source("Contracts", "contract.yaml#customers", model=model)
    unmapped_sources = source.read_external_sources(
        "Contracts", "contract.yaml#customers", model=model
    )
    assert unmapped_sources[0].mapping[0].sourceDataType.type == "VendorType"
    source_config = model.dataSources.get("Contracts").entity
    type_config = model.dataSourceTypes.get(source_config.type).entity
    type_config.dataTypeMapping = [
        *type_config.dataTypeMapping,
        SourceDataTypeMapping(sourceType="VendorType", targetType="short"),
    ]
    source_config.dataTypeMapping = [
        SourceDataTypeMapping(sourceType=" vendortype ", targetType="long")
    ]
    for _ in range(2):
        entity = source.read_from_data_source("Contracts", "contract.yaml#customers", model=model)
        assert [attr.dataType.type for attr in entity.attributes] == ["long", "long", "long"]
        assert [mapping.sourceDataType.type for mapping in entity.sources[0].mapping] == [
            "VendorType",
            "VendorType",
            "BIGINT",
        ]


def test_unmapped_source_is_readable_but_import_description_returns_validation_error(
    tmp_path, builtin_environment
):
    write_contract(
        tmp_path / "contract.yaml",
        contract(
            [{"name": "customer_id", "physicalType": "VendorInteger", "logicalType": "integer"}]
        ),
    )
    config.set_solution(
        create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.yaml"})])
    )
    factory._model = factory.create_model()
    with TestClient(create_app()) as client:
        params = {"source_location": "contract.yaml#customers"}
        metadata = client.get("/sources/Contracts/locations/metadata", params=params)
        assert metadata.status_code == 200
        assert metadata.json()["items"][0]["dataType"] == "VendorInteger"
        response = client.get("/sources/Contracts/locations/import-description", params=params)
        assert response.status_code == 400, response.text
        for context in ("Contracts", "contract.yaml#customers", "customer_id", "VendorInteger"):
            assert context in response.text
