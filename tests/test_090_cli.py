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

import re
from pathlib import Path

from pytest_cases import parametrize_with_cases
from test_090_cli_cases import CasesCli
from typer.testing import CliRunner, Result

from datam8.app import app

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _common_cli_assert(result: Result):
    assert result.exit_code == 0, f"Exit code was {result.exit_code}, expected 0"


def _run_cli(args: list[str], solution_path: Path) -> Result:
    return CliRunner().invoke(app, [*args, "-s", solution_path.as_posix()])


@parametrize_with_cases(
    "command_name",
    cases=CasesCli,
    glob="*top_level*",
)
def test_cli_print_help_text(command_name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(app, [command_name, "-h"])

    help_text = f"Usage: datam8 {command_name}"

    assert help_text in result.output, f"'{help_text}' was not part of {result.output}"
    _common_cli_assert(result)


def test_cli_list(solution_file_path: Path) -> None:
    result = _run_cli(["list"], solution_file_path)
    result_lines = result.output.splitlines()

    assert result_lines[0].endswith("entities in total"), (
        f"The first line of the output must be a summary: [{result_lines[0]}]"
    )
    _common_cli_assert(result)


def test_cli_show(solution_file_path: Path) -> None:
    result_of_list = _run_cli(["list"], solution_file_path)
    # last line of output should be a model entity's locator
    locator = result_of_list.output.splitlines()[-1]

    result = _run_cli(["show", locator], solution_file_path)
    result_lines = result.output.splitlines()

    assert result_lines[0].startswith("File: "), (
        f"The first line of the output must be the file path: {result_lines[0]}"
    )
    _common_cli_assert(result)


def test_cli_validate(solution_file_path: Path) -> None:
    result = CliRunner().invoke(app, ["validate", "-s", solution_file_path.as_posix()])
    result_lines = result.output.splitlines()

    assert result_lines[-1] == "Validation successfull", (
        f"Validation did not finish successfully, output: {result_lines}"
    )
    _common_cli_assert(result)


def test_cli_generate(solution_file_path: Path) -> None:
    result = CliRunner().invoke(app, ["generate", "-s", solution_file_path.as_posix()])
    result_lines = result.output.splitlines()

    assert result_lines[-1] == "Generation successfull", (
        f"Generation did not finish successfully, output: {result_lines}"
    )
    _common_cli_assert(result)


# @parametrize_with_cases(
#     "case_data",
#     cases=CasesCli,
#     glob="*missing_solution*",
# )
# def test_generate_validate_serve_stay_single_call_commands(case_data, monkeypatch) -> None:
#     runner = CliRunner()
#     monkeypatch.delenv("DATAM8_SOLUTION_PATH", raising=False)
#
#     command_name, expected_text = case_data
#     result = runner.invoke(app, [command_name])
#     assert result.exit_code != 0
#     assert expected_text in _normalized_output(result)
#
#     serve_help = runner.invoke(app, ["serve", "--help"])
#     assert serve_help.exit_code == 0
#     assert "--token" in _normalized_output(serve_help)
#
#     serve = runner.invoke(app, ["serve"])
#     assert serve.exit_code != 0
#
#
# def test_solution_full_includes_folder_entities_in_cli(tmp_path: Path) -> None:
#     runner = CliRunner()
#     solution_file = _create_solution_with_folder_metadata(tmp_path)
#
#     result = runner.invoke(
#         app,
#         ["solution", "full", "--json", "--solution", str(solution_file)],
#     )
#     assert result.exit_code == 0
#     payload = json.loads(result.stdout)
#     assert "folderEntities" in payload
#     assert len(payload["folderEntities"]) == 1
#     assert payload["folderEntities"][0]["folderPath"] == "010-Stage/Sales"
#
#
# def test_model_folder_rename_returns_refreshed_entities(tmp_path: Path) -> None:
#     runner = CliRunner()
#     solution_file = _create_solution_with_folder_metadata(tmp_path, folder_name="Old")
#     from_rel = "Model/010-Stage/Old"
#     to_rel = "Model/010-Stage/New"
#
#     result = runner.invoke(
#         app,
#         [
#             "model",
#             "folder-rename",
#             from_rel,
#             to_rel,
#             "--json",
#             "--solution",
#             str(solution_file),
#         ],
#     )
#     assert result.exit_code == 0
#     payload = json.loads(result.stdout)
#     assert payload["status"] == "renamed"
#     assert payload["toAbsPath"].replace("\\", "/").endswith(to_rel)
#     assert "index" in payload
#     assert len(payload["entities"]) == 1
#     assert payload["entities"][0]["relPath"] == "Model/010-Stage/New/Customer.json"
#
#
# def test_model_folder_metadata_get_save_delete(tmp_path: Path) -> None:
#     runner = CliRunner()
#     solution_file = _create_solution_with_folder_metadata(tmp_path)
#     rel_path = "Model/010-Stage/Sales/.properties.json"
#
#     get_result = runner.invoke(
#         app,
#         [
#             "model",
#             "folder-metadata",
#             "get",
#             rel_path,
#             "--json",
#             "--solution",
#             str(solution_file),
#         ],
#     )
#     assert get_result.exit_code == 0
#     get_payload = json.loads(get_result.stdout)
#     assert get_payload["content"]["name"] == "Sales"
#
#     save_payload = {
#         "id": 777,
#         "name": "Sales",
#         "displayName": "Sales Folder",
#         "properties": [],
#     }
#     save_result = runner.invoke(
#         app,
#         [
#             "model",
#             "folder-metadata",
#             "save",
#             rel_path,
#             json.dumps(save_payload),
#             "--json",
#             "--solution",
#             str(solution_file),
#         ],
#     )
#     assert save_result.exit_code == 0
#
#     get_after_save = runner.invoke(
#         app,
#         [
#             "model",
#             "folder-metadata",
#             "get",
#             rel_path,
#             "--json",
#             "--solution",
#             str(solution_file),
#         ],
#     )
#     assert get_after_save.exit_code == 0
#     after_payload = json.loads(get_after_save.stdout)
#     assert after_payload["content"]["id"] == 777
#     assert after_payload["content"]["displayName"] == "Sales Folder"
#
#     delete_result = runner.invoke(
#         app,
#         [
#             "model",
#             "folder-metadata",
#             "delete",
#             rel_path,
#             "--json",
#             "--solution",
#             str(solution_file),
#         ],
#     )
#     assert delete_result.exit_code == 0
#     assert not (tmp_path / rel_path).exists()
