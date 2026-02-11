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
import shutil
from pathlib import Path

from pytest_cases import parametrize_with_cases
from test_100_server_integration_cases import CasesServerIntegration


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


def _copy_solution_subset(
    *,
    source_solution_path: Path,
    destination_root: Path,
    target_name: str,
) -> Path:
    source_root = source_solution_path.parent
    solution = json.loads(source_solution_path.read_text(encoding="utf-8"))

    required_dirs = {
        str(solution.get("basePath") or "").strip(),
        str(solution.get("modelPath") or "").strip(),
    }
    for target in solution.get("generatorTargets") or []:
        if not isinstance(target, dict):
            continue
        if target.get("name") != target_name:
            continue
        source_path = target.get("sourcePath")
        if isinstance(source_path, str) and source_path.strip():
            required_dirs.add(source_path.strip())
        break

    destination_root.mkdir(parents=True, exist_ok=True)
    copied_solution_path = destination_root / source_solution_path.name
    copied_solution_path.write_text(
        source_solution_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    ignore = shutil.ignore_patterns(".git", ".venv", "node_modules", "__pycache__", ".pytest_cache")
    for rel_dir in sorted({d for d in required_dirs if d}):
        src = source_root / rel_dir
        dst = destination_root / rel_dir
        if not src.exists():
            continue
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)

    return copied_solution_path


@parametrize_with_cases(
    "case_data",
    cases=CasesServerIntegration,
)
def test_serve_readiness_auth_and_generate_sync(
    case_data,
    solution_file_path: Path,
    tmp_path: Path,
    api_client,
) -> None:
    log_level, clean_output = case_data
    token = "test-token"
    target, output_path = _select_target(solution_file_path)

    work = tmp_path / "solution"
    copied_solution_path = _copy_solution_subset(
        source_solution_path=solution_file_path,
        destination_root=work,
        target_name=target,
    )

    with api_client(token=token, solution_path=copied_solution_path) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

        response = client.get("/version")
        assert response.status_code == 200
        assert isinstance(response.json().get("version"), str)

        response = client.get("/config")
        assert response.status_code == 401

        response = client.post(
            "/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "solutionPath": str(copied_solution_path),
                "target": target,
                "logLevel": log_level,
                "cleanOutput": clean_output,
            },
        )
        response.raise_for_status()
        result = response.json()
        assert result.get("status") == "succeeded"

    output_dir = work / output_path
    assert output_dir.exists(), f"Expected output directory at {output_dir}"
    assert any(p.is_file() for p in output_dir.rglob("*")), (
        f"Expected generated files in {output_dir}"
    )
