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

from pytest_cases import parametrize_with_cases
from test_080_workspace_io_cases import CasesWorkspaceIo

from datam8.core import workspace_io


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_solution(
    tmp_path: Path,
    old_folder_rel: str,
) -> Path:
    base = tmp_path / "Base"
    old_entity = tmp_path / Path(old_folder_rel) / "Customer.json"

    _write_json(
        base / "DataProducts.json",
        {"type": "dataProducts", "dataProducts": [{"name": "Default", "dataModules": [{"name": "Default"}]}]},
    )
    _write_json(
        old_entity,
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
        tmp_path / Path(old_folder_rel) / ".properties.json",
        {
            "id": 10,
            "name": "Old",
            "dataProduct": "Sales",
            "dataModule": "Customer",
            "properties": [],
        },
    )
    _write_json(
        tmp_path / "TestSolution.dm8s",
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
    return tmp_path / "TestSolution.dm8s"


def test_regenerate_index_with_entities_matches_regenerate_index(tmp_path: Path) -> None:
    solution_path = _create_solution(tmp_path, "Model/010-Stage/Old")

    index_only = workspace_io.regenerate_index(str(solution_path))
    index_with_entities, entities = workspace_io.regenerate_index_with_entities(str(solution_path))

    assert index_only == index_with_entities
    assert len(entities) == 1
    assert entities[0].name == "Customer"


def test_list_folder_entities_scans_properties_files(tmp_path: Path) -> None:
    solution_path = _create_solution(tmp_path, "Model/010-Stage/Old")

    model_entities = workspace_io.list_model_entities(str(solution_path))
    folder_entities = workspace_io.list_folder_entities(str(solution_path))

    assert len(model_entities) == 1
    assert len(folder_entities) == 1
    assert folder_entities[0].relPath.endswith(".properties.json")
    assert folder_entities[0].folderPath == "010-Stage/Old"
    assert folder_entities[0].name == "Old"


@parametrize_with_cases(
    "case_data",
    cases=CasesWorkspaceIo,
)
def test_model_folder_rename_uses_single_model_entity_scan(case_data, monkeypatch, tmp_path: Path, api_client) -> None:
    old_folder_rel, new_folder_rel, expected_entity_count = case_data
    solution_path = _create_solution(tmp_path, old_folder_rel)
    token = "scan-opt-token"

    original = workspace_io.list_model_entities
    calls = {"count": 0}

    def _counted(solution: str | None):
        calls["count"] += 1
        return original(solution)

    monkeypatch.setattr(workspace_io, "list_model_entities", _counted)

    with api_client(token=token, solution_path=solution_path) as client:
        response = client.post(
            "/model/folder/rename",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "fromFolderRelPath": old_folder_rel,
                "toFolderRelPath": new_folder_rel,
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        response.raise_for_status()
        payload = response.json()

    assert calls["count"] == 1
    assert payload["message"] == "renamed"
    assert payload["to"].replace("\\", "/").endswith(new_folder_rel)
    assert len(payload["entities"]) == expected_entity_count
