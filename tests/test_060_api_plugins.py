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
import json
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


def _build_fixture_wheel(
    fixture_connector_plugins_dir: Path,
    connector_id: str,
    wheel_name: str,
) -> bytes:
    root = fixture_connector_plugins_dir / "connectors" / connector_id
    if not root.exists():
        raise RuntimeError(f"Missing fixture at {root}")

    plugin_json = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    entrypoint = str(plugin_json.get("entrypoint") or "").strip()
    if ":" not in entrypoint:
        raise RuntimeError("fixture plugin.json entrypoint is invalid")
    module_name, _attr = entrypoint.split(":", 1)
    module_path = Path(*module_name.split("."))
    package_dir = module_path.parent
    connector_source = root / "src" / module_path.with_suffix(".py")
    connector_init = root / "src" / package_dir / "__init__.py"
    if not connector_source.exists():
        raise RuntimeError(f"Missing fixture connector source: {connector_source}")

    wheel_stem = wheel_name[:-4]
    wheel_parts = wheel_stem.split("-")
    if len(wheel_parts) < 5:
        raise RuntimeError("fixture wheel_name must follow PEP 427 pattern")
    distribution = wheel_parts[0]
    version = wheel_parts[1]
    dist_info = f"{distribution}-{version}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{package_dir.as_posix()}/__init__.py",
            connector_init.read_text(encoding="utf-8") if connector_init.exists() else "",
        )
        zf.writestr(module_path.with_suffix(".py").as_posix(), connector_source.read_text(encoding="utf-8"))
        zf.writestr(
            f"{dist_info}.dist-info/METADATA",
            "\n".join(
                [
                    "Metadata-Version: 2.1",
                    f"Name: {distribution}",
                    f"Version: {version}",
                    "",
                ]
            ),
        )
        zf.writestr(
            f"{dist_info}.dist-info/WHEEL",
            "\n".join(
                [
                    "Wheel-Version: 1.0",
                    "Generator: datam8-tests",
                    "Root-Is-Purelib: true",
                    "Tag: py3-none-any",
                    "",
                ]
            ),
        )
        zf.writestr(
            f"{dist_info}.dist-info/entry_points.txt",
            f"[datam8.connectors]\n{connector_id} = {entrypoint}\n",
        )
        zf.writestr(f"{dist_info}.dist-info/RECORD", "")
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
    connector_id, wheel_name = case_data
    token = "test-token"
    wheel_bytes = _build_fixture_wheel(fixture_connector_plugins_dir, connector_id, wheel_name)
    headers = {"Authorization": f"Bearer {token}"}

    with api_client(token=token, plugin_dir=temp_plugin_dir) as client:
        response = client.get("/connectors", headers=headers)
        response.raise_for_status()
        assert connector_id not in _connector_ids(response.json())

        response = client.post(
            "/plugins/install",
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
                "x-file-name": wheel_name,
            },
            content=wheel_bytes,
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
                "Content-Type": "application/octet-stream",
                "x-file-name": wheel_name,
            },
            content=wheel_bytes,
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
            {"id": "fake-connector", "capabilities": {"validateConnection": True}},
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


def test_plugins_install_rejects_zip_payload(api_client) -> None:
    token = "plugins-install-reject-zip"
    headers = {"Authorization": f"Bearer {token}"}

    with api_client(token=token) as client:
        response = client.post(
            "/plugins/install",
            headers={**headers, "Content-Type": "application/zip", "x-file-name": "legacy.zip"},
            content=b"PK\x03\x04",
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload.get("code") == "connector_distribution_invalid"


def test_datasource_list_tables_requires_metadata_capability(api_client, monkeypatch) -> None:
    token = "datasource-capability-missing"
    headers = {"Authorization": f"Bearer {token}"}

    class _FakeConnector:
        @staticmethod
        def list_tables(cfg, resolver):  # pragma: no cover - should not be called
            _ = cfg
            _ = resolver
            return []

    monkeypatch.setattr(
        "datam8.api.routes.api_connectors.secrets_core.get_runtime_secrets_map",
        lambda solution_path, data_source_name, include_values: {},
    )
    monkeypatch.setattr(
        "datam8.api.routes.api_connectors.connector_resolve.resolve_and_validate",
        lambda solution_path, data_source_id, runtime_secrets: (
            _FakeConnector,
            {
                "id": "fake-connector",
                "capabilities": {
                    "uiSchema": False,
                    "validateConnection": False,
                    "metadata": {"listTables": False, "getTableMetadata": False},
                    "runtimeQuery": {"sql": False, "dataFrame": False},
                },
            },
            {"config": True},
            {"resolver": True},
        ),
    )

    with api_client(token=token) as client:
        response = client.post(
            "/datasources/SampleDataSource/list-tables",
            headers=headers,
            json={"solutionPath": "C:/tmp/TestSolution.dm8s", "runtimeSecrets": {"password": "x"}},
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload.get("code") == "connector_capability_missing"
