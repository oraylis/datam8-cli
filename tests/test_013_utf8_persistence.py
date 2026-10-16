import asyncio
import json
from pathlib import Path

import pytest
from builtin_plugins.solution import create_solution
from fastapi.testclient import TestClient
from jinja2 import Template
from test_019_odcs import write_contract
from test_019_odcs_cases import contract

from datam8 import config, factory
from datam8.api.app import create_app
from datam8.generate import GeneratorConfig, render_template
from datam8.migration_v1 import MigrationV1
from datam8.plugins.builtins.odcs import OdcsFile
from datam8_model.base import BaseEntities, Properties

DESCRIPTION = "Topic für Beschwerden – Größe 東京"


def test_migration_writes_utf8(tmp_path):
    MigrationV1.create_new_properties([DESCRIPTION], tmp_path)

    saved = json.loads((tmp_path / "property_values.json").read_bytes().decode("utf-8"))
    assert saved["propertyValues"][0]["name"] == DESCRIPTION


@pytest.mark.parametrize("model_class", [Properties, BaseEntities])
def test_base_json_utf8_roundtrip(tmp_path, model_class):
    payload = {
        "type": "properties",
        "properties": [{"name": "Comment", "displayName": DESCRIPTION}],
    }
    path = tmp_path / "Properties.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = model_class.from_json_file(path)
    loaded.to_json_file(path, "w", {"exclude_none": True})

    assert json.loads(path.read_bytes().decode("utf-8")) == payload
    assert model_class.from_json_file(path) == loaded
    assert DESCRIPTION.encode("utf-8") in path.read_bytes()


def test_base_delete_keeps_remaining_text_utf8(tmp_path, builtin_environment):
    path = create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.json"})])
    properties = tmp_path / "Base/Properties.json"
    properties.write_text(
        json.dumps(
            {
                "type": "properties",
                "properties": [
                    {"name": "Keep", "displayName": DESCRIPTION},
                    {"name": "Remove", "displayName": "Remove"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    config.set_solution(path)
    factory._model = factory.create_model()

    with TestClient(create_app()) as client:
        assert client.delete("/entities/properties/Remove").status_code == 200
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200

    saved = json.loads(properties.read_bytes().decode("utf-8"))
    assert saved["properties"] == [{"name": "Keep", "displayName": DESCRIPTION}]


@pytest.mark.parametrize("import_path", ["direct", "wizard"])
def test_import_refresh_reload_and_output_preserve_utf8(tmp_path, builtin_environment, import_path):
    data = contract([{"name": "topic", "logicalType": "string", "description": DESCRIPTION}])
    contract_path = tmp_path / "contract.json"
    write_contract(contract_path, data)
    path = create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.json"})])
    config.set_solution(path)
    factory._model = factory.create_model()
    locator = "modelEntities/Stage/Topics"
    entity_path = tmp_path / "Model/Stage/Topics.json"

    with TestClient(create_app()) as client:
        if import_path == "direct":
            response = client.put(
                "/sources/Contracts/import",
                json={"locator": locator, "sourceLocation": "contract.json#customers"},
            )
        else:
            response = client.get(
                "/sources/Contracts/locations/import-description",
                params={"source_location": "contract.json#customers"},
            )
            assert response.status_code == 200, response.text
            response = client.put("/entities/" + locator, json=response.json()["entity"])
            assert response.status_code == 200, response.text
            response = client.post("/model/save")
        assert response.status_code in (200, 204), response.text
        assert (
            json.loads(entity_path.read_bytes().decode("utf-8"))["attributes"][0]["description"]
            == DESCRIPTION
        )
        assert client.post("/model/reload").status_code == 200

        updated = DESCRIPTION + " geändert"
        data["schema"][0]["properties"][0]["description"] = updated
        data["schema"][0]["properties"].append(
            {"name": "added", "logicalType": "string", "description": DESCRIPTION}
        )
        write_contract(contract_path, data)
        response = client.get(
            "/sources/compare", params={"locator": locator, "mode": "sources-only"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["wrapper"]["entity"]["attributes"][0]["description"] == DESCRIPTION

        response = client.get("/sources/compare", params={"locator": locator, "mode": "complete"})
        assert response.status_code == 200, response.text
        refreshed = response.json()["wrapper"]["entity"]
        response = client.patch("/entities/" + locator, json=refreshed)
        assert response.status_code == 200, response.text
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
        response = client.get("/entities/" + locator)
        assert response.status_code == 200, response.text
        reloaded = response.json()["items"][0]["entity"]
        saved = json.loads(entity_path.read_bytes().decode("utf-8"))
        for entity in (reloaded, saved):
            assert [a["description"] for a in entity["attributes"]] == [updated, DESCRIPTION]

        result = asyncio.run(
            render_template(
                "utf8",
                data=reloaded,
                template=Template("{{ data.attributes[0].description }}"),
                output_path=Path("topic.sql"),
                _config=GeneratorConfig(
                    target=factory.get_model().get_generator_target("test"),
                    payloads=[],
                    generate_all=False,
                    clean_output=False,
                ),
            )
        )
        assert result is None
        assert (tmp_path / "Output/topic.sql").read_bytes() == updated.encode("utf-8")
