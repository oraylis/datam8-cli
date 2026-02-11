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
from pathlib import Path

from typer.testing import CliRunner

from datam8.app import app


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_minimal_solution(root: Path) -> Path:
    base_path = root / "Base"
    model_path = root / "Model"
    generate_path = root / "Generate" / "dummy" / "__modules"
    output_path = root / "Output" / "dummy" / "generated"
    base_path.mkdir(parents=True, exist_ok=True)
    model_path.mkdir(parents=True, exist_ok=True)
    generate_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    _write_json(base_path / "DataProducts.json", {"type": "dataProducts", "dataProducts": []})
    _write_json(
        model_path / "Customer.json",
        {
            "id": 1,
            "name": "Customer",
            "attributes": [],
            "sources": [],
        },
    )

    solution = {
        "schemaVersion": "2.0.0",
        "basePath": "Base",
        "modelPath": "Model",
        "generatorTargets": [
            {
                "name": "dummy",
                "isDefault": True,
                "sourcePath": "Generate/dummy",
                "outputPath": "Output/dummy/generated",
            }
        ],
    }
    solution_file = root / "TestSolution.dm8s"
    _write_json(solution_file, solution)
    return solution_file


def test_cli_help_exposes_top_level_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in (
        "solution",
        "base",
        "model",
        "script",
        "index",
        "refactor",
        "search",
        "connector",
        "plugin",
        "secret",
        "datasource",
        "config",
        "migration",
        "fs",
        "generate",
        "validate",
        "serve",
    ):
        assert name in result.stdout


def test_solution_base_model_commands_use_root_cli_options(tmp_path: Path) -> None:
    runner = CliRunner()
    solution_file = _create_minimal_solution(tmp_path)

    result = runner.invoke(
        app,
        [
            "solution",
            "info",
            "--json",
            "--solution",
            str(solution_file),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["solution"]["schemaVersion"] == "2.0.0"

    result = runner.invoke(
        app,
        ["base", "list", "--json", "--solution", str(solution_file)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1

    result = runner.invoke(
        app,
        ["model", "list", "--json", "--solution", str(solution_file)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1


def test_generate_validate_serve_stay_single_call_commands(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.delenv("DATAM8_SOLUTION_PATH", raising=False)

    generate = runner.invoke(app, ["generate"])
    assert generate.exit_code != 0
    assert "No solution specified." in f"{generate.stdout}\n{generate.stderr}"

    validate = runner.invoke(app, ["validate"])
    assert validate.exit_code != 0
    assert "No solution specified." in f"{validate.stdout}\n{validate.stderr}"

    serve = runner.invoke(app, ["serve"])
    assert serve.exit_code != 0
    assert "Missing option '--token'" in f"{serve.stdout}\n{serve.stderr}"
