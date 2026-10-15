import json

import pytest
from builtin_plugins.solution import create_solution
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app
from datam8.plugins.builtins.file import CsvFile


@pytest.mark.parametrize("auth", [{}, {"authMode": "no_auth"}])
def test_csv_repeated_operations_preserve_connection_options(tmp_path, builtin_plugin, auth):
    (tmp_path / "orders.csv").write_text("id;name\n1;Müller\n2;Weiß\n", encoding="utf-8")
    properties = {"path": str(tmp_path), "separator": ";", **auth}
    plugin = builtin_plugin(CsvFile, properties)
    original = dict(plugin.extended_properties)
    for _ in range(2):
        assert plugin.test_connection() is None
        assert plugin.list_source()["object"].to_list() == ["orders.csv"]
        fields = list(plugin.get_table_metadata("orders.csv").iter_source_fields())
        assert [(field.name, field.dataType) for field in fields] == [
            ("id", "number"),
            ("name", "string"),
        ]
        assert plugin.preview_data("orders.csv", limit=1).collect().to_dicts() == [
            {"id": 1, "name": "Müller"}
        ]
        assert plugin.extended_properties == original
        assert plugin._data_source.extendedProperties == properties


def test_csv_auth_mode_http_metadata_preview_import_and_reload(tmp_path, builtin_environment):
    directory = tmp_path / "csv/nested"
    directory.mkdir(parents=True)
    (directory / "orders.csv").write_text("id,name\n1,Müller\n2,Weiß\n", encoding="utf-8")
    solution = create_solution(
        tmp_path, [(CsvFile, "Csv", {"path": str(tmp_path / "csv"), "authMode": "no_auth"})]
    )
    config.set_solution(solution)
    factory._model = factory.create_model()
    with TestClient(create_app()) as client:
        assert client.get("/sources/Csv/test").status_code == 200
        directory_response = client.get("/sources/Csv/locations")
        assert directory_response.status_code == 200, directory_response.text
        folder = directory_response.json()["items"][0]
        listed = client.get(
            "/sources/Csv/locations", params={"source_location": folder["sourceLocation"]}
        )
        assert listed.status_code == 200, listed.text
        location = listed.json()["items"][0]["sourceLocation"]
        for _ in range(2):
            metadata = client.get(
                "/sources/Csv/locations/metadata", params={"source_location": location}
            )
            assert metadata.status_code == 200, metadata.text
            assert metadata.json()["count"] == 2
            preview = client.get(
                "/sources/Csv/locations/preview", params={"source_location": location, "limit": 1}
            )
            assert preview.status_code == 200, preview.text
            assert preview.json()["items"] == [{"id": 1, "name": "Müller"}]
        imported = client.put(
            "/sources/Csv/import",
            json={"locator": "modelEntities/Stage/Orders", "sourceLocation": location},
        )
        assert imported.status_code == 200, imported.text
        saved = json.loads((tmp_path / "Model/Stage/Orders.json").read_text())
        assert [attribute["name"] for attribute in saved["attributes"]] == ["id", "name"]
        assert saved["sources"][0]["sourceLocation"] == "nested/orders.csv"
        assert client.post("/model/reload", params={"force": True}).status_code == 200
        source = json.loads((tmp_path / "Base/DataSources.json").read_text())["dataSources"][0]
        assert source["extendedProperties"]["authMode"] == "no_auth"
