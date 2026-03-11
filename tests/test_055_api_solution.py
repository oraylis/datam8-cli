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

import base64
import io
import json
import zipfile
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel_path, content in entries.items():
            archive.writestr(rel_path, content)
    return buffer.getvalue()


def _create_solution(tmp_path: Path) -> Path:
    base = tmp_path / "Base"
    model = tmp_path / "Model" / "010-Stage" / "Sales"
    _write_json(
        base / "DataProducts.json",
        {"type": "dataProducts", "dataProducts": [{"name": "Default", "dataModules": [{"name": "Default"}]}]},
    )
    _write_json(
        model / "Customer.json",
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
    assert payload["folderEntities"][0]["content"]["name"] == "Sales"


def test_solution_full_and_save_keep_model_entity_sparse(tmp_path: Path, api_client) -> None:
    token = "solution-sparse-token"
    solution_path = _create_solution(tmp_path)
    entity_rel = "Model/010-Stage/Sales/Customer.json"
    entity_path = tmp_path / entity_rel

    with api_client(token=token, solution_path=solution_path) as client:
        full_response = client.get(
            "/solution/full",
            params={"path": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        full_response.raise_for_status()
        full_payload = full_response.json()
        model_entity = next(e for e in full_payload["modelEntities"] if e["relPath"] == entity_rel)
        first_attribute = model_entity["content"]["attributes"][0]

        assert "history" not in first_attribute
        assert "expressionLanguage" not in first_attribute
        assert "isBusinessKey" not in first_attribute

        save_response = client.post(
            "/model/entities",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": entity_rel,
                "content": {**model_entity["content"], "description": "Updated by UI"},
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        save_response.raise_for_status()

    written = json.loads(entity_path.read_text(encoding="utf-8"))
    written_attr = written["attributes"][0]
    assert written.get("description") == "Updated by UI"
    assert "history" not in written_attr
    assert "expressionLanguage" not in written_attr
    assert "isBusinessKey" not in written_attr


def test_solution_new_project_accepts_targets_list_json(tmp_path: Path, api_client) -> None:
    token = "solution-new-project-json-token"

    with api_client(token=token) as client:
        response = client.post(
            "/solution/new-project",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "solutionName": "ApiMultiTarget",
                "projectRoot": str(tmp_path),
                "basePath": "Base",
                "modelPath": "Model",
                "targets": [
                    {"name": "databricks"},
                    {"name": "sqlserver", "isDefault": True},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()

    solution_path = Path(payload["solutionPath"])
    assert solution_path.exists()
    content = json.loads(solution_path.read_text(encoding="utf-8"))
    assert len(content["generatorTargets"]) == 2
    assert content["generatorTargets"][1]["name"] == "sqlserver"
    assert content["generatorTargets"][1]["isDefault"] is True


def test_solution_new_project_accepts_multipart_target_zip(tmp_path: Path, api_client) -> None:
    token = "solution-new-project-multipart-token"
    zip_bytes = _build_zip({"__modules/payloads.py": "def payload():\n    return []\n"})

    payload = {
        "solutionName": "ApiZipTarget",
        "projectRoot": str(tmp_path),
        "basePath": "Base",
        "modelPath": "Model",
        "targets": [
            {"name": "ziptarget", "zipField": "zip_target_0"},
        ],
    }

    with api_client(token=token) as client:
        response = client.post(
            "/solution/new-project",
            headers={"Authorization": f"Bearer {token}"},
            data={"payload": json.dumps(payload)},
            files={"zip_target_0": ("ziptarget.zip", zip_bytes, "application/zip")},
        )
        response.raise_for_status()
        body = response.json()

    solution_path = Path(body["solutionPath"])
    assert solution_path.exists()
    assert (solution_path.parent / "Generate" / "ziptarget" / "__modules" / "payloads.py").exists()


def test_solution_new_project_accepts_json_base64_target_zip(tmp_path: Path, api_client) -> None:
    token = "solution-new-project-json-zip-token"
    zip_bytes = _build_zip({"scripts/run.sql": "select 1;"})

    with api_client(token=token) as client:
        response = client.post(
            "/solution/new-project",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "solutionName": "ApiZipTargetJson",
                "projectRoot": str(tmp_path),
                "basePath": "Base",
                "modelPath": "Model",
                "targets": [{"name": "ziptarget"}],
                "targetArchives": {"0": base64.b64encode(zip_bytes).decode("ascii")},
            },
        )
        response.raise_for_status()
        body = response.json()

    solution_path = Path(body["solutionPath"])
    assert solution_path.exists()
    assert (solution_path.parent / "Generate" / "ziptarget" / "scripts" / "run.sql").exists()


def test_solution_new_project_requires_at_least_one_target(tmp_path: Path, api_client) -> None:
    token = "solution-new-project-no-target-token"

    with api_client(token=token) as client:
        response = client.post(
            "/solution/new-project",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "solutionName": "ApiNoTarget",
                "projectRoot": str(tmp_path),
                "basePath": "Base",
                "modelPath": "Model",
            },
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["message"] == "At least one target is required."


def test_solution_new_project_keeps_legacy_target_field(tmp_path: Path, api_client) -> None:
    token = "solution-new-project-legacy-token"

    with api_client(token=token) as client:
        response = client.post(
            "/solution/new-project",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "solutionName": "ApiLegacyTarget",
                "projectRoot": str(tmp_path),
                "target": "legacy",
            },
        )
        response.raise_for_status()
        payload = response.json()

    solution_path = Path(payload["solutionPath"])
    content = json.loads(solution_path.read_text(encoding="utf-8"))
    assert len(content["generatorTargets"]) == 1
    assert content["generatorTargets"][0]["name"] == "legacy"
