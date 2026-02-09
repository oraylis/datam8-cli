from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _solution_path_from_env() -> Path:
    raw = os.environ.get("DATAM8_SOLUTION_PATH", "").strip()
    if not raw:
        pytest.skip("Set DATAM8_SOLUTION_PATH to run server/jobs integration test.")

    p = Path(raw)
    if p.is_file() and p.suffix.lower() == ".dm8s":
        return p
    if p.is_dir():
        dm8s_files = sorted(p.glob("*.dm8s"))
        if len(dm8s_files) == 1:
            return dm8s_files[0]
        pytest.skip(f"Expected exactly one .dm8s file in {p}, found {len(dm8s_files)}.")
    pytest.skip(f"DATAM8_SOLUTION_PATH points to a missing or invalid path: {p}")


def _select_target(solution_path: Path) -> tuple[str, Path]:
    solution = json.loads(solution_path.read_text(encoding="utf-8"))
    targets = solution.get("generatorTargets")
    if not isinstance(targets, list) or len(targets) == 0:
        raise RuntimeError(f"No generatorTargets found in {solution_path}")

    selected: dict | None = None
    for target in targets:
        if isinstance(target, dict) and target.get("isDefault") is True:
            selected = target
            break
    if selected is None:
        for target in targets:
            if isinstance(target, dict) and isinstance(target.get("name"), str) and target["name"].strip():
                selected = target
                break
    if selected is None:
        raise RuntimeError(f"Could not select a generator target from {solution_path}")

    name = selected.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(f"Selected target has no valid name in {solution_path}")
    output_path = selected.get("outputPath")
    if not isinstance(output_path, str) or not output_path.strip():
        output_path = f"Output/{name}"
    return name, Path(output_path)


def _spawn_server(*, token: str, solution_path: Path) -> tuple[subprocess.Popen[bytes], dict]:
    repo_root = _repo_root()
    env = {**os.environ, "PYTHONPATH": str(repo_root / "src"), "DATAM8_JOB_CONCURRENCY": "1"}
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
        "--solution-path",
        str(solution_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    assert proc.stdout is not None
    line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
    payload = json.loads(line)
    assert payload["type"] == "ready"
    assert payload["baseUrl"].startswith("http://127.0.0.1:")
    assert isinstance(payload.get("version"), str)
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


def _wait_for_status(client: httpx.Client, *, base_url: str, token: str, job_id: str, timeout_s: int = 120) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"{base_url}/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        data = r.json()
        if data.get("status") in {"succeeded", "failed", "canceled"}:
            return data
        time.sleep(0.2)
    raise TimeoutError("Job did not finish in time.")


def test_serve_readiness_auth_and_generate_job_sse() -> None:
    token = "test-token"
    source_solution_path = _solution_path_from_env()
    source_solution_dir = source_solution_path.parent
    target, output_path = _select_target(source_solution_path)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "solution"
        shutil.copytree(source_solution_dir, work)
        solution_path = work / source_solution_path.name

        proc, ready = _spawn_server(token=token, solution_path=solution_path)
        try:
            base_url = ready["baseUrl"]

            with httpx.Client(timeout=30.0) as client:
                # Public health/version.
                r = client.get(f"{base_url}/health")
                assert r.status_code == 200
                assert r.json().get("status") == "ok"

                r = client.get(f"{base_url}/version")
                assert r.status_code == 200
                assert isinstance(r.json().get("version"), str)

                # Auth required for protected routes.
                r = client.get(f"{base_url}/api/config")
                assert r.status_code == 401

                # Create a generate job.
                r = client.post(
                    f"{base_url}/jobs",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "type": "generate",
                        "params": {
                            "solutionPath": str(solution_path),
                            "target": target,
                            "logLevel": "info",
                            "cleanOutput": True,
                        },
                    },
                )
                r.raise_for_status()
                job_id = r.json()["jobId"]
                assert job_id

                # SSE: ensure we receive at least one log event and terminal status.
                seen_log = False
                terminal = None
                with client.stream(
                    "GET",
                    f"{base_url}/jobs/{job_id}/events",
                    headers={"Authorization": f"Bearer {token}"},
                ) as s:
                    s.raise_for_status()
                    event_name = None
                    data_lines: list[str] = []
                    for raw in s.iter_lines():
                        if raw is None:
                            continue
                        line = raw.strip("\r")
                        if line.startswith(":"):
                            continue
                        if not line:
                            if event_name and data_lines:
                                payload = json.loads("".join(data_lines))
                                if event_name == "log":
                                    seen_log = True
                                if event_name == "status" and payload.get("status") in {"succeeded", "failed", "canceled"}:
                                    terminal = payload.get("status")
                                    break
                            event_name = None
                            data_lines = []
                            continue
                        if line.startswith("event:"):
                            event_name = line.split(":", 1)[1].strip()
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line.split(":", 1)[1].strip())
                            continue

                assert seen_log is True
                assert terminal == "succeeded"

                meta = _wait_for_status(client, base_url=base_url, token=token, job_id=job_id)
                assert meta["status"] == "succeeded"

                output_dir = work / output_path
                assert output_dir.exists(), f"Expected output directory at {output_dir}"
                assert any(p.is_file() for p in output_dir.rglob("*")), (
                    f"Expected generated files in {output_dir}"
                )

        finally:
            _terminate(proc)
