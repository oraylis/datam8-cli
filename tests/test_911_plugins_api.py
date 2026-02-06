from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx


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


def _spawn_server(*, token: str, plugin_dir: Path) -> tuple[subprocess.Popen[bytes], dict]:
    repo_root = _repo_root()
    env = {
        **os.environ,
        "PYTHONPATH": str(repo_root / "src"),
        "DATAM8_JOB_CONCURRENCY": "1",
        "DATAM8_PLUGIN_DIR": str(plugin_dir),
    }
    cmd = [
        sys.executable,
        "-m",
        "datam8",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--token",
        token,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    assert proc.stdout is not None
    line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
    payload = json.loads(line)
    assert payload["type"] == "ready"
    return proc, payload


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


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

    with tempfile.TemporaryDirectory() as td:
        plugin_dir = Path(td) / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        proc, ready = _spawn_server(token=token, plugin_dir=plugin_dir)
        try:
            base_url = ready["baseUrl"]
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=20.0) as client:
                r = client.get(f"{base_url}/api/connectors", headers=headers)
                r.raise_for_status()
                assert "test-conn" not in _connector_ids(r.json())

                r = client.post(
                    f"{base_url}/api/plugins/install",
                    headers={**headers, "Content-Type": "application/zip", "x-file-name": "test-conn.zip"},
                    content=zip_bytes,
                )
                r.raise_for_status()
                state = r.json()
                ids = [p.get("id") for p in (state.get("plugins") or []) if isinstance(p, dict)]
                assert "test-conn" in ids

                r = client.get(f"{base_url}/api/connectors", headers=headers)
                r.raise_for_status()
                assert "test-conn" in _connector_ids(r.json())

                r = client.post(f"{base_url}/api/plugins/disable", headers=headers, json={"id": "test-conn"})
                r.raise_for_status()
                r = client.get(f"{base_url}/api/connectors", headers=headers)
                r.raise_for_status()
                assert "test-conn" not in _connector_ids(r.json())

                r = client.post(f"{base_url}/api/plugins/enable", headers=headers, json={"id": "test-conn"})
                r.raise_for_status()
                r = client.get(f"{base_url}/api/connectors", headers=headers)
                r.raise_for_status()
                assert "test-conn" in _connector_ids(r.json())

                r = client.post(f"{base_url}/api/plugins/uninstall", headers=headers, json={"id": "test-conn"})
                r.raise_for_status()
                r = client.get(f"{base_url}/api/connectors", headers=headers)
                r.raise_for_status()
                assert "test-conn" not in _connector_ids(r.json())

        finally:
            _terminate(proc)
