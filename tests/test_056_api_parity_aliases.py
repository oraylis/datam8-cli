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
        {"type": "folders", "folders": [{"id": 101, "name": "Sales", "properties": []}]},
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


def test_solution_info_and_validate_aliases(tmp_path: Path, api_client) -> None:
    token = "alias-token"
    solution_path = _create_solution(tmp_path)

    with api_client(token=token, solution_path=solution_path) as client:
        info = client.get(
            "/solution/info",
            params={"path": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        info.raise_for_status()
        info_payload = info.json()

        validate = client.post(
            "/solution/validate",
            params={"path": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        validate.raise_for_status()
        validate_payload = validate.json()

        full_validate = client.post(
            "/validate",
            params={"path": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert full_validate.status_code == 400
        full_validate_payload = full_validate.json()

    assert info_payload["solutionPath"].endswith("TestSolution.dm8s")
    assert info_payload["solution"]["schemaVersion"] == "2.0.0"
    assert validate_payload["status"] == "ok"
    assert validate_payload["solutionPath"].endswith("TestSolution.dm8s")
    error_code = full_validate_payload.get("code") or full_validate_payload.get("error", {}).get("code")
    assert error_code == "validation_error"


def test_base_entity_alias_get_set_patch(tmp_path: Path, api_client) -> None:
    token = "base-alias-token"
    solution_path = _create_solution(tmp_path)

    with api_client(token=token, solution_path=solution_path) as client:
        get_before = client.get(
            "/base/entity",
            params={"relPath": "Base/DataProducts.json", "solutionPath": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        get_before.raise_for_status()
        assert get_before.json()["content"]["dataProducts"] == []

        set_resp = client.post(
            "/base/entity/set",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": "Base/DataProducts.json",
                "pointer": "/dataProducts/0",
                "value": {"name": "Sales", "dataModules": []},
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        set_resp.raise_for_status()

        patch_resp = client.post(
            "/base/entity/patch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": "Base/DataProducts.json",
                "patch": {
                    "dataProducts": [
                        {
                            "name": "Sales",
                            "dataModules": [{"name": "Customer"}],
                        }
                    ]
                },
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        patch_resp.raise_for_status()

        get_after = client.get(
            "/base/entity",
            params={"relPath": "Base/DataProducts.json", "solutionPath": str(solution_path)},
            headers={"Authorization": f"Bearer {token}"},
        )
        get_after.raise_for_status()
        payload = get_after.json()

    assert payload["content"]["dataProducts"][0]["name"] == "Sales"
    assert payload["content"]["dataProducts"][0]["dataModules"][0]["name"] == "Customer"


def test_model_entity_aliases_and_folder_metadata_aliases(tmp_path: Path, api_client) -> None:
    token = "model-alias-token"
    solution_path = _create_solution(tmp_path)

    with api_client(token=token, solution_path=solution_path) as client:
        create_resp = client.post(
            "/model/entity/create",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": "Model/010-Stage/Sales/Order.json",
                "name": "Order",
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        create_resp.raise_for_status()

        get_resp = client.get(
            "/model/entity",
            params={
                "selector": "Model/010-Stage/Sales/Order.json",
                "by": "relPath",
                "solutionPath": str(solution_path),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        get_resp.raise_for_status()
        assert get_resp.json()["content"]["name"] == "Order"

        validate_resp = client.post(
            "/model/entity/validate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "selector": "Model/010-Stage/Sales/Order.json",
                "by": "relPath",
                "solutionPath": str(solution_path),
            },
        )
        validate_resp.raise_for_status()
        assert validate_resp.json()["status"] == "ok"

        set_resp = client.post(
            "/model/entity/set",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "selector": "Model/010-Stage/Sales/Order.json",
                "by": "relPath",
                "pointer": "/id",
                "value": 2,
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        set_resp.raise_for_status()

        patch_resp = client.post(
            "/model/entity/patch",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "selector": "Model/010-Stage/Sales/Order.json",
                "by": "relPath",
                "patch": {"name": "OrderRenamed"},
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        patch_resp.raise_for_status()

        duplicate_resp = client.post(
            "/model/entity/duplicate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "fromRelPath": "Model/010-Stage/Sales/Order.json",
                "toRelPath": "Model/010-Stage/Sales/OrderCopy.json",
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        duplicate_resp.raise_for_status()
        assert duplicate_resp.json()["message"] == "duplicated"

        folder_get = client.get(
            "/model/folder-metadata",
            params={
                "relPath": "Model/010-Stage/Sales/.properties.json",
                "solutionPath": str(solution_path),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        folder_get.raise_for_status()
        assert folder_get.json()["content"]["type"] == "folders"

        folder_save = client.post(
            "/model/folder-metadata",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": "Model/010-Stage/Sales/.properties.json",
                "content": {
                    "type": "folders",
                    "folders": [{"id": 999, "name": "Sales", "properties": []}],
                },
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        folder_save.raise_for_status()

        folder_delete = client.request(
            "DELETE",
            "/model/folder-metadata",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "relPath": "Model/010-Stage/Sales/.properties.json",
                "solutionPath": str(solution_path),
                "noLock": True,
            },
        )
        folder_delete.raise_for_status()

    assert (tmp_path / "Model/010-Stage/Sales/OrderCopy.json").exists()
    assert not (tmp_path / "Model/010-Stage/Sales/.properties.json").exists()
