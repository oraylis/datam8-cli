from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from datam8.core.validation import validate_solution_dm8s
from datam8_model.solution import Solution

from conftest import TestConfig


def _copy_solution(solution_file: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    solution = Solution.from_json_file(solution_file)
    source_root = solution_file.parent

    copied_solution = destination / solution_file.name
    shutil.copy2(solution_file, copied_solution)

    for rel_dir in (solution.basePath, solution.modelPath):
        src = source_root / rel_dir
        dst = destination / rel_dir
        if src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)

    return copied_solution


def _first_model_entity_file(dm8s_path: Path) -> Path:
    solution = Solution.from_json_file(dm8s_path)
    model_root = dm8s_path.parent / solution.modelPath
    files = sorted(path for path in model_root.rglob("*.json") if path.name != ".properties.json")
    if not files:
        raise RuntimeError(f"No model entity JSON files found under {model_root}")
    return files[0]


def test_validate_solution_dm8s_ok(config: TestConfig) -> None:
    report = asyncio.run(validate_solution_dm8s(config.solution_file_path))

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["summary"]["entitiesParsed"] > 0
    assert report["summary"]["modelEntitiesParsed"] > 0


def test_validate_solution_dm8s_failure_returns_errors(config: TestConfig, tmp_path: Path) -> None:
    copied_dm8s = _copy_solution(config.solution_file_path, tmp_path / "broken-solution")
    model_entity_file = _first_model_entity_file(copied_dm8s)

    content = json.loads(model_entity_file.read_text(encoding="utf-8"))
    if "id" in content:
        content.pop("id", None)
    else:
        content["name"] = 12345
    model_entity_file.write_text(json.dumps(content, indent=2), encoding="utf-8")

    report = asyncio.run(validate_solution_dm8s(copied_dm8s))

    assert report["ok"] is False
    assert len(report["errors"]) > 0
    assert report["errors"][0]["code"] in {"PARSING_ERROR", "SCHEMA_ERROR", "RESOLVE_ERROR", "UNKNOWN_ERROR"}
