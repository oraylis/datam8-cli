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

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from datam8.api.app import create_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_plugins_dir() -> Path:
    p = _repo_root() / "tests" / "fixtures" / "connector_plugins"
    if not p.exists():
        raise RuntimeError(f"Missing fixture at {p}")
    return p


@contextmanager
def _client(*, token: str, plugin_dir: Path):
    previous_tempdir = tempfile.tempdir
    previous = {
        "DATAM8_PLUGIN_DIR": os.environ.get("DATAM8_PLUGIN_DIR"),
        "TMPDIR": os.environ.get("TMPDIR"),
        "TMP": os.environ.get("TMP"),
        "TEMP": os.environ.get("TEMP"),
    }
    os.environ["DATAM8_PLUGIN_DIR"] = str(plugin_dir)
    temp_root = str(plugin_dir.parent)
    os.environ["TMPDIR"] = temp_root
    os.environ["TMP"] = temp_root
    os.environ["TEMP"] = temp_root
    tempfile.tempdir = temp_root
    try:
        app = create_app(token=token, enable_openapi=False)
        with TestClient(app) as client:
            yield client
    finally:
        tempfile.tempdir = previous_tempdir
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_connectors_endpoints_plugins_only() -> None:
    token = "test-token"
    fixture = _fixture_plugins_dir()
    with tempfile.TemporaryDirectory(dir=str(_repo_root())) as td:
        plugin_dir = Path(td) / "plugins"
        shutil.copytree(fixture, plugin_dir)

        headers = {"Authorization": f"Bearer {token}"}
        with _client(token=token, plugin_dir=plugin_dir) as client:
            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            data = r.json()
            connectors = data.get("connectors") or []
            assert any(c.get("id") == "test-conn" for c in connectors)

            r = client.get("/connectors/test-conn/ui-schema", headers=headers)
            r.raise_for_status()
            schema = r.json()
            assert schema.get("connectorId") == "test-conn"
            assert schema.get("schema", {}).get("authModes")

            r = client.post(
                "/connectors/test-conn/validate-connection",
                headers=headers,
                json={"solutionPath": None, "extendedProperties": {"host": "localhost", "password": ""}},
            )
            r.raise_for_status()
            out = r.json()
            assert out.get("ok") is False
            assert any(e.get("key") == "password" for e in out.get("errors") or [])
