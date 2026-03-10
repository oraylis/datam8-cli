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

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datam8 import config as datam8_config
from datam8 import factory


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_minimal_solution(root: Path) -> Path:
    _write_json(
        root / "Base" / "DataProducts.json",
        {
            "type": "dataProducts",
            "dataProducts": [
                {"name": "Default", "dataModules": [{"name": "Default"}]},
            ],
        },
    )
    _write_json(
        root / "Model" / "Customer.json",
        {
            "id": 1,
            "name": "Customer",
            "attributes": [
                {
                    "ordinalNumber": 10,
                    "name": "id",
                    "attributeType": "Physical",
                    "dataType": {"type": "int", "nullable": False},
                    "dateAdded": "2024-01-01T00:00:00Z",
                }
            ],
            "sources": [],
            "transformations": [],
            "relationships": [],
        },
    )
    _write_json(
        root / "TestSolution.dm8s",
        {
            "schemaVersion": "2.0.0",
            "basePath": "Base",
            "modelPath": "Model",
            "generatorTargets": [
                {
                    "name": "dummy",
                    "isDefault": True,
                    "sourcePath": "Generate/dummy",
                    "outputPath": "Output/dummy/generated",
                }
            ],
        },
    )
    return root / "TestSolution.dm8s"


def _model_entity_payload(attribute_name: str) -> dict:
    return {
        "attributes": [
            {
                "ordinalNumber": 10,
                "name": attribute_name,
                "attributeType": "Physical",
                "dataType": {"type": "int", "nullable": False},
                "dateAdded": "2024-01-01T00:00:00Z",
            }
        ],
        "sources": [],
        "transformations": [],
        "relationships": [],
    }


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    factory._model = None
    previous_run_as_api = datam8_config.run_as_api
    datam8_config.run_as_api = True
    yield
    factory._model = None
    datam8_config.run_as_api = previous_run_as_api


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _activate_solution(solution_file: Path) -> None:
    datam8_config.solution_path = solution_file
    datam8_config.solution_folder_path = solution_file.parent


def test_create_model_entity_is_persisted_via_save_body_locator(
    api_client, tmp_path: Path
) -> None:
    solution_file = _create_minimal_solution(tmp_path)
    _activate_solution(solution_file)
    model_file = tmp_path / "Model" / "NewCustomer.json"

    with api_client(token="test-token", solution_path=solution_file) as client:
        create_response = client.put(
            "/entities/modelEntities/NewCustomer",
            headers=_headers(),
            json=_model_entity_payload("newId"),
        )
        assert create_response.status_code == 200

        get_response = client.get("/entities/modelEntities/NewCustomer", headers=_headers())
        assert get_response.status_code == 200
        assert len(get_response.json()) == 1
        assert get_response.json()[0]["locator"]["entityName"] == "NewCustomer"

        unsaved = client.get("/model/unsaved", headers=_headers())
        assert unsaved.status_code == 200
        assert unsaved.json() == ["modelEntities/NewCustomer"]

        save_response = client.post(
            "/model/save",
            headers=_headers(),
            json={"locator": "modelEntities/NewCustomer"},
        )
        assert save_response.status_code == 200

    assert model_file.exists()
    payload = json.loads(model_file.read_text(encoding="utf-8"))
    assert payload["name"] == "NewCustomer"


def test_model_save_without_locator_persists_all_unsaved_model_entities(
    api_client, tmp_path: Path
) -> None:
    solution_file = _create_minimal_solution(tmp_path)
    _activate_solution(solution_file)
    left_file = tmp_path / "Model" / "CustomerLeft.json"
    right_file = tmp_path / "Model" / "CustomerRight.json"

    with api_client(token="test-token", solution_path=solution_file) as client:
        left_response = client.put(
            "/entities/modelEntities/CustomerLeft",
            headers=_headers(),
            json=_model_entity_payload("leftId"),
        )
        assert left_response.status_code == 200

        right_response = client.put(
            "/entities/modelEntities/CustomerRight",
            headers=_headers(),
            json=_model_entity_payload("rightId"),
        )
        assert right_response.status_code == 200

        unsaved = client.get("/model/unsaved", headers=_headers())
        assert unsaved.status_code == 200
        assert unsaved.json() == [
            "modelEntities/CustomerLeft",
            "modelEntities/CustomerRight",
        ]

        save_response = client.post("/model/save", headers=_headers())
        assert save_response.status_code == 200

        unsaved_after = client.get("/model/unsaved", headers=_headers())
        assert unsaved_after.status_code == 200
        assert unsaved_after.json() == []

    assert left_file.exists()
    assert right_file.exists()
