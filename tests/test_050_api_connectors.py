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

import shutil
from pathlib import Path

from pytest_cases import parametrize_with_cases
from test_050_api_connectors_cases import CasesConnectorValidation


def _connector_ids(payload: dict) -> list[str]:
    connectors = payload.get("connectors") or []
    out: list[str] = []
    for item in connectors:
        if isinstance(item, dict):
            cid = item.get("id")
            if isinstance(cid, str):
                out.append(cid)
    return out


def test_connectors_list_and_ui_schema(
    fixture_connector_plugins_dir: Path,
    temp_plugin_dir: Path,
    api_client,
) -> None:
    token = "test-token"
    shutil.copytree(fixture_connector_plugins_dir, temp_plugin_dir, dirs_exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}

    with api_client(token=token, plugin_dir=temp_plugin_dir) as client:
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert "test-conn" in _connector_ids(response.json())

        response = client.get("/connectors/test-conn/ui-schema", headers=headers)
        response.raise_for_status()
        payload = response.json()
        assert payload.get("connectorId") == "test-conn"
        assert payload.get("schema", {}).get("authModes")


@parametrize_with_cases(
    "case_data",
    cases=CasesConnectorValidation,
)
def test_connectors_validate_connection(case_data, fixture_connector_plugins_dir: Path, temp_plugin_dir: Path, api_client) -> None:
    connector_id, body, expected_error_key = case_data
    token = "test-token"
    shutil.copytree(fixture_connector_plugins_dir, temp_plugin_dir, dirs_exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}

    with api_client(token=token, plugin_dir=temp_plugin_dir) as client:
        response = client.post(
            f"/connectors/{connector_id}/validate-connection",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        assert payload.get("ok") is False
        assert any(e.get("key") == expected_error_key for e in (payload.get("errors") or []))
