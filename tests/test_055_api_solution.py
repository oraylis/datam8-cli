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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_solution(tmp_path: Path) -> Path:
    base = tmp_path / "Base"
    model = tmp_path / "Model" / "010-Stage" / "Sales"
    _write_json(base / "DataProducts.json", {"type": "dataProducts", "dataProducts": []})
    _write_json(model / "Customer.json", {"id": 1, "name": "Customer", "attributes": [], "sources": []})
    _write_json(
        model / ".properties.json",
        {
            "type": "folders",
            "folders": [{"id": 101, "name": "Sales", "properties": []}],
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


def test_solution_full_includes_folder_entities(tmp_path: Path, api_client) -> None:
    token = "solution-token"
    solution_path = _create_solution(tmp_path)

    with api_client(token=token, solution_path=solution_path) as client:
        response = client.get(
            "/solution/full",
            params={"path": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()

    assert "folderEntities" in payload
    assert len(payload["folderEntities"]) == 1
    assert payload["folderEntities"][0]["folderPath"] == "010-Stage/Sales"
    assert payload["folderEntities"][0]["content"]["type"] == "folders"
