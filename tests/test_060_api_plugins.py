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

import io
import zipfile
from pathlib import Path

from pytest_cases import parametrize_with_cases
from test_060_api_plugins_cases import CasesPluginLifecycle


def _connector_ids(payload: dict) -> list[str]:
    connectors = payload.get("connectors") or []
    out: list[str] = []
    for item in connectors:
        if isinstance(item, dict):
            cid = item.get("id")
            if isinstance(cid, str):
                out.append(cid)
    return out


def _build_fixture_zip(fixture_connector_plugins_dir: Path, connector_id: str) -> bytes:
    root = fixture_connector_plugins_dir / "connectors" / connector_id
    if not root.exists():
        raise RuntimeError(f"Missing fixture at {root}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            arc = Path(connector_id) / file_path.relative_to(root)
            zf.write(file_path, arc.as_posix())
    return buf.getvalue()


@parametrize_with_cases(
    "case_data",
    cases=CasesPluginLifecycle,
)
def test_plugins_api_install_enable_disable_uninstall(
    case_data,
    fixture_connector_plugins_dir: Path,
    temp_plugin_dir: Path,
    api_client,
) -> None:
    connector_id, zip_name = case_data
    token = "test-token"
    zip_bytes = _build_fixture_zip(fixture_connector_plugins_dir, connector_id)
    headers = {"Authorization": f"Bearer {token}"}

    with api_client(token=token, plugin_dir=temp_plugin_dir) as client:
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id not in _connector_ids(response.json())

        response = client.post(
            "/plugins/install",
            headers={
                **headers,
                "Content-Type": "application/zip",
                "x-file-name": zip_name,
            },
            content=zip_bytes,
        )
        response.raise_for_status()
        state = response.json()
        installed_ids = [p.get("id") for p in (state.get("plugins") or []) if isinstance(p, dict)]
        assert connector_id in installed_ids

        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id in _connector_ids(response.json())

        response = client.post("/plugins/disable", headers=headers, json={"id": connector_id})
        response.raise_for_status()
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id not in _connector_ids(response.json())

        response = client.post("/plugins/enable", headers=headers, json={"id": connector_id})
        response.raise_for_status()
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id in _connector_ids(response.json())

        response = client.get(f"/plugins/{connector_id}/info", headers=headers)
        response.raise_for_status()
        assert response.json().get("plugin", {}).get("id") == connector_id

        response = client.post(f"/plugins/{connector_id}/verify", headers=headers)
        response.raise_for_status()
        assert isinstance(response.json().get("verified"), bool)

        response = client.post(
            "/plugins/verify",
            headers={
                **headers,
                "Content-Type": "application/zip",
            },
            content=zip_bytes,
        )
        response.raise_for_status()
        assert response.json().get("verified") is True

        response = client.post("/plugins/uninstall", headers=headers, json={"id": connector_id})
        response.raise_for_status()
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id not in _connector_ids(response.json())


def test_datasource_test_endpoint_calls_connector_test(api_client, monkeypatch) -> None:
    token = "datasource-test-token"
    headers = {"Authorization": f"Bearer {token}"}
    called: dict[str, bool] = {"test": False}

    class _FakeConnector:
        @staticmethod
        def test_connection(cfg, resolver) -> None:
            _ = cfg
            _ = resolver
            called["test"] = True

    monkeypatch.setattr(
        "datam8.api.routes.api_connectors.secrets_core.get_runtime_secrets_map",
        lambda solution_path, data_source_name, include_values: {},
    )
    monkeypatch.setattr(
        "datam8.api.routes.api_connectors.connector_resolve.resolve_and_validate",
        lambda solution_path, data_source_id, runtime_secrets: (
            _FakeConnector,
            {"id": "fake-connector"},
            {"config": True},
            {"resolver": True},
        ),
    )

    with api_client(token=token) as client:
        response = client.post(
            "/datasources/SampleDataSource/test",
            headers=headers,
            json={"solutionPath": "C:/tmp/TestSolution.dm8s", "runtimeSecrets": {"password": "x"}},
        )
        response.raise_for_status()
        payload = response.json()

    assert payload["status"] == "ok"
    assert payload["connector"] == "fake-connector"
    assert called["test"] is True
