from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_plugins_dir() -> Path:
    p = _repo_root() / "tests" / "fixtures" / "connector_plugins"
    if not p.exists():
        raise RuntimeError(f"Missing fixture at {p}")
    return p


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


def test_connectors_endpoints_plugins_only() -> None:
    token = "test-token"
    fixture = _fixture_plugins_dir()
    with tempfile.TemporaryDirectory() as td:
        pd = Path(td) / "plugins"
        shutil.copytree(fixture, pd)

        proc, ready = _spawn_server(token=token, plugin_dir=pd)
        try:
            base_url = ready["baseUrl"]
            with httpx.Client(timeout=20.0) as client:
                r = client.get(f"{base_url}/api/connectors", headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                data = r.json()
                connectors = data.get("connectors") or []
                assert any(c.get("id") == "test-conn" for c in connectors)

                r = client.get(
                    f"{base_url}/api/connectors/test-conn/ui-schema",
                    headers={"Authorization": f"Bearer {token}"},
                )
                r.raise_for_status()
                schema = r.json()
                assert schema.get("connectorId") == "test-conn"
                assert schema.get("schema", {}).get("authModes")

                r = client.post(
                    f"{base_url}/api/connectors/test-conn/validate-connection",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"solutionPath": None, "extendedProperties": {"host": "localhost", "password": ""}},
                )
                r.raise_for_status()
                out = r.json()
                assert out.get("ok") is False
                assert any(e.get("key") == "password" for e in out.get("errors") or [])

        finally:
            _terminate(proc)

