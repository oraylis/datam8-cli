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
import re
from pathlib import Path

from pytest_cases import parametrize_with_cases
from test_090_cli_cases import CasesCli
from typer.testing import CliRunner

from datam8.app import app

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


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


def _normalized_output(result) -> str:
    chunks: list[bytes] = []
    stdout_bytes = getattr(result, "stdout_bytes", None)
    stderr_bytes = getattr(result, "stderr_bytes", None)
    if isinstance(stdout_bytes, (bytes, bytearray)):
        chunks.append(bytes(stdout_bytes))
    if isinstance(stderr_bytes, (bytes, bytearray)):
        chunks.append(bytes(stderr_bytes))

    if chunks:
        text = b"\n".join(chunks).decode("utf-8", errors="ignore")
    else:
        text = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"

    return _ANSI_ESCAPE_RE.sub("", text).lower()


@parametrize_with_cases(
    "command_name",
    cases=CasesCli,
    glob="*top_level*",
)
def test_cli_help_exposes_top_level_commands(command_name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert command_name in result.stdout


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


@parametrize_with_cases(
    "case_data",
    cases=CasesCli,
    glob="*missing_solution*",
)
def test_generate_validate_serve_stay_single_call_commands(case_data, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.delenv("DATAM8_SOLUTION_PATH", raising=False)

    command_name, expected_text = case_data
    result = runner.invoke(app, [command_name])
    assert result.exit_code != 0
    assert expected_text in _normalized_output(result)

    serve_help = runner.invoke(app, ["serve", "--help"])
    assert serve_help.exit_code == 0
    assert "--token" in _normalized_output(serve_help)

    serve = runner.invoke(app, ["serve"])
    assert serve.exit_code != 0
