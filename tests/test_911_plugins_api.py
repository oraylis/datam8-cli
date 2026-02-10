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
import os
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from datam8.api.app import create_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_connector_dir() -> Path:
    p = _repo_root() / "tests" / "fixtures" / "connector_plugins" / "connectors" / "test-conn"
    if not p.exists():
        raise RuntimeError(f"Missing fixture at {p}")
    return p


def _build_fixture_zip() -> bytes:
    root = _fixture_connector_dir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            arc = Path("test-conn") / file_path.relative_to(root)
            zf.write(file_path, arc.as_posix())
    return buf.getvalue()


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


def _connector_ids(payload: dict) -> list[str]:
    connectors = payload.get("connectors") or []
    out: list[str] = []
    for item in connectors:
        if isinstance(item, dict):
            cid = item.get("id")
            if isinstance(cid, str):
                out.append(cid)
    return out


def test_plugins_api_install_enable_disable_uninstall() -> None:
    token = "test-token"
    zip_bytes = _build_fixture_zip()

    with tempfile.TemporaryDirectory(dir=str(_repo_root())) as td:
        plugin_dir = Path(td) / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        headers = {"Authorization": f"Bearer {token}"}
        with _client(token=token, plugin_dir=plugin_dir) as client:
            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            assert "test-conn" not in _connector_ids(r.json())

            r = client.post(
                "/plugins/install",
                headers={**headers, "Content-Type": "application/zip", "x-file-name": "test-conn.zip"},
                content=zip_bytes,
            )
            r.raise_for_status()
            state = r.json()
            ids = [p.get("id") for p in (state.get("plugins") or []) if isinstance(p, dict)]
            assert "test-conn" in ids

            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            assert "test-conn" in _connector_ids(r.json())

            r = client.post("/plugins/disable", headers=headers, json={"id": "test-conn"})
            r.raise_for_status()
            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            assert "test-conn" not in _connector_ids(r.json())

            r = client.post("/plugins/enable", headers=headers, json={"id": "test-conn"})
            r.raise_for_status()
            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            assert "test-conn" in _connector_ids(r.json())

            r = client.post("/plugins/uninstall", headers=headers, json={"id": "test-conn"})
            r.raise_for_status()
            r = client.get("/connectors", headers=headers)
            r.raise_for_status()
            assert "test-conn" not in _connector_ids(r.json())
