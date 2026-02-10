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
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datam8.api.app import create_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _solution_path_from_env() -> Path:
    raw = os.environ.get("DATAM8_SOLUTION_PATH", "").strip()
    if not raw:
        pytest.skip("Set DATAM8_SOLUTION_PATH to run server integration tests.")

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


@contextmanager
def _client(*, token: str, solution_path: Path):
    previous = os.environ.get("DATAM8_SOLUTION_PATH")
    os.environ["DATAM8_SOLUTION_PATH"] = str(solution_path)
    try:
        app = create_app(token=token, enable_openapi=False)
        with TestClient(app) as client:
            yield client
    finally:
        if previous is None:
            os.environ.pop("DATAM8_SOLUTION_PATH", None)
        else:
            os.environ["DATAM8_SOLUTION_PATH"] = previous


def test_serve_readiness_auth_and_generate_sync() -> None:
    token = "test-token"
    source_solution_path = _solution_path_from_env()
    source_solution_dir = source_solution_path.parent
    target, output_path = _select_target(source_solution_path)

    with tempfile.TemporaryDirectory(dir=str(_repo_root())) as td:
        work = Path(td) / "solution"
        shutil.copytree(source_solution_dir, work)
        solution_path = work / source_solution_path.name

        with _client(token=token, solution_path=solution_path) as client:
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json().get("status") == "ok"

            r = client.get("/version")
            assert r.status_code == 200
            assert isinstance(r.json().get("version"), str)

            r = client.get("/config")
            assert r.status_code == 401

            r = client.post(
                "/generate",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "solutionPath": str(solution_path),
                    "target": target,
                    "logLevel": "info",
                    "cleanOutput": True,
                },
            )
            r.raise_for_status()
            result = r.json()
            assert result.get("status") == "succeeded"

            output_dir = work / output_path
            assert output_dir.exists(), f"Expected output directory at {output_dir}"
            assert any(p.is_file() for p in output_dir.rglob("*")), (
                f"Expected generated files in {output_dir}"
            )
