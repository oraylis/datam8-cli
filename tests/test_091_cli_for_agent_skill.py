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

import json
import shutil
from pathlib import Path

import polars as pl
import pytest
from config import DataM8TestConfig
from typer.testing import CliRunner, Result

from datam8 import factory
from datam8.app import app
from datam8.cmd import entities


def _copy_solution(tmp_path: Path, config: DataM8TestConfig) -> Path:
    target = tmp_path / "solution"
    shutil.copytree(config.solution_file_path.parent, target)
    return target / config.solution_file_path.name


def _run(args: list[str], solution_path: Path) -> Result:
    return CliRunner().invoke(app, [*args, "-s", solution_path.as_posix()])


def _json(result: Result) -> dict:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _show(locator: str, solution_path: Path) -> dict:
    result = _run(["show", locator, "--json"], solution_path)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["--version"],
        ["list", "--help"],
        ["list-by-property", "--help"],
        ["show", "--help"],
        ["validate", "--help"],
        ["generate", "--help"],
        ["init", "--help"],
        ["serve", "--help"],
        ["sources", "--help"],
        ["plugins", "--help"],
        ["secrets", "--help"],
        ["migrate", "--help"],
        ["entities", "--help"],
        ["entities", "create", "--help"],
        ["entities", "patch", "--help"],
        ["entities", "delete", "--help"],
        ["entities", "clone", "--help"],
        ["entities", "move", "--help"],
        ["entities", "import", "--help"],
        ["entities", "import", "external", "--help"],
        ["entities", "import", "internal", "--help"],
    ],
)
def test_cli_help_and_registration(args: list[str]) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output


def test_sources_import_is_not_public() -> None:
    help_result = CliRunner().invoke(app, ["sources", "--help"])
    assert help_result.exit_code == 0
    assert " import " not in help_result.output

    import_result = CliRunner().invoke(app, ["sources", "import"])
    assert import_result.exit_code != 0
    assert "entities import external" not in import_result.output


def test_parse_set_options() -> None:
    parsed = entities._parse_set_options(
        [
            "description=Customer master data",
            "expression=a=b",
            "enabled=true",
            "disabled=false",
            "missing=null",
            "sortOrder=123",
            "ratio=12.5",
            'tags=["a"]',
            'meta={"x":1}',
        ]
    )
    assert parsed == {
        "description": "Customer master data",
        "expression": "a=b",
        "enabled": True,
        "disabled": False,
        "missing": None,
        "sortOrder": 123,
        "ratio": 12.5,
        "tags": ["a"],
        "meta": {"x": 1},
    }


@pytest.mark.parametrize("value", ["invalid", "=value"])
def test_parse_set_options_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        entities._parse_set_options([value])


def test_parse_body_rejects_invalid_json_body_and_modes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        entities._parse_body(set_options=None, body_path=None, json_body="{")
    with pytest.raises(ValueError):
        entities._parse_body(set_options=None, body_path=None, json_body="[1]")
    with pytest.raises(ValueError):
        entities._parse_body(set_options=["x=1"], body_path=tmp_path / "body.json", json_body=None)
    with pytest.raises(ValueError):
        entities._parse_body(set_options=None, body_path=None, json_body=None)
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError):
        entities._parse_body(set_options=None, body_path=missing, json_body=None)
    array_body = tmp_path / "array.json"
    array_body.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError):
        entities._parse_body(set_options=None, body_path=array_body, json_body=None)


def test_entities_create_patch_clone_move_delete_json_flow(
    tmp_path: Path, config: DataM8TestConfig
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    source = "modelEntities/020-Core/CliTest/CreatedCustomer"
    clone = "modelEntities/020-Core/CliTest/CreatedCustomerCopy"
    moved = "modelEntities/020-Core/CliSandbox/CreatedCustomerCopy"

    created = _json(
        _run(
            [
                "entities",
                "create",
                source,
                "--set",
                "description=Created via CLI",
                "--json",
            ],
            solution_path,
        )
    )
    assert created["operation"] == "create"
    shown = _show(source, solution_path)
    assert shown["name"] == "CreatedCustomer"
    assert shown["id"] > 0
    assert shown["description"] == "Created via CLI"

    patched = _json(
        _run(
            ["entities", "patch", source, "--set", "description=Updated via CLI", "--json"],
            solution_path,
        )
    )
    assert patched["operation"] == "patch"
    assert _show(source, solution_path)["description"] == "Updated via CLI"

    cloned = _json(_run(["entities", "clone", source, clone, "--json"], solution_path))
    assert cloned["new_locator"] == clone
    assert _show(source, solution_path)["name"] == "CreatedCustomer"
    assert _show(clone, solution_path)["name"] == "CreatedCustomerCopy"

    moved_result = _json(_run(["entities", "move", clone, moved, "--json"], solution_path))
    assert moved_result["to_locator"] == moved
    assert _run(["show", clone, "--json"], solution_path).exit_code != 0
    assert _show(moved, solution_path)["name"] == "CreatedCustomerCopy"

    scope = _run(["list", moved, "--json"], solution_path)
    assert scope.exit_code == 0
    deleted = _json(_run(["entities", "delete", moved, "--yes", "--json"], solution_path))
    assert deleted["deleted"] == [moved]
    assert _run(["show", moved, "--json"], solution_path).exit_code != 0
    assert _run(["validate"], solution_path).exit_code == 0


def test_delete_without_yes_prompts_and_can_abort(tmp_path: Path, config: DataM8TestConfig) -> None:
    solution_path = _copy_solution(tmp_path, config)
    locator = "modelEntities/020-Core/CliTest/DeletePrompt"
    _run(["entities", "create", locator, "--set", "description=x", "--json"], solution_path)
    result = CliRunner().invoke(
        app,
        ["entities", "delete", locator, "-s", solution_path.as_posix()],
        input="n\n",
    )
    assert result.exit_code != 0
    assert _run(["show", locator, "--json"], solution_path).exit_code == 0


def test_entity_commands_default_output_is_human_readable(
    tmp_path: Path, config: DataM8TestConfig
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    locator = "modelEntities/020-Core/CliTest/HumanOutput"

    create_result = _run(
        ["entities", "create", locator, "--set", "description=human"], solution_path
    )
    assert create_result.exit_code == 0, create_result.output
    assert create_result.output.startswith("Created entity at ")
    assert not create_result.output.lstrip().startswith("{")

    patch_result = _run(
        ["entities", "patch", locator, "--set", "description=human updated"], solution_path
    )
    assert patch_result.exit_code == 0, patch_result.output
    assert patch_result.output.startswith("Patched entity at ")
    assert not patch_result.output.lstrip().startswith("{")


def test_move_moves_function_directory(tmp_path: Path, config: DataM8TestConfig) -> None:
    solution_path = _copy_solution(tmp_path, config)
    source = "modelEntities/020-Core/CliTest/FuncEntity"
    target = "modelEntities/020-Core/CliSandbox/FuncEntity"
    _run(["entities", "create", source, "--set", "description=x", "--json"], solution_path)

    source_dir = solution_path.parent / "Model/020-Core/CliTest/FuncEntity"
    target_dir = solution_path.parent / "Model/020-Core/CliSandbox/FuncEntity"
    function_file = source_dir / "transform.py"
    source_dir.mkdir(parents=True, exist_ok=True)
    function_file.write_text("def transform():\n    pass\n", encoding="utf-8")

    result = _run(["entities", "move", source, target, "--json"], solution_path)
    assert result.exit_code == 0, result.output
    assert not function_file.exists()
    assert (target_dir / "transform.py").read_text(encoding="utf-8").startswith("def transform")


def test_internal_import(tmp_path: Path, config: DataM8TestConfig) -> None:
    solution_path = _copy_solution(tmp_path, config)
    source = "modelEntities/020-Core/Sales/Customer/Customer"
    target = "modelEntities/020-Core/CliTest/InternalCustomer"

    result = _json(
        _run(
            [
                "entities",
                "import",
                "internal",
                target,
                "--source-locator",
                source,
                "--json",
            ],
            solution_path,
        )
    )
    assert result["operation"] == "import-internal"
    target_entity = _show(target, solution_path)
    source_entity = _show(source, solution_path)
    assert target_entity["sources"][0]["sourceLocation"] == source_entity["id"]
    assert len(target_entity["attributes"]) == len(source_entity["attributes"])
    assert target_entity["relationships"] == []
    assert target_entity["transformations"] == []


def test_external_import_with_fake_plugin(
    tmp_path: Path, config: DataM8TestConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    target = "modelEntities/020-Core/CliTest/ExternalCustomer"

    class FakePlugin:
        def get_table_metadata(self, table: str, schema: str | None = None) -> pl.DataFrame:
            assert table == "Customer"
            assert schema == "Sales"
            return pl.DataFrame(
                [
                    {"name": "CustomerID", "ordinal": 1, "dataType": "int", "isNullable": False},
                    {"name": "Name", "ordinal": 2, "dataType": "varchar", "isNullable": True},
                ]
            )

    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda _name: FakePlugin())
    result = _json(
        _run(
            [
                "entities",
                "import",
                "external",
                target,
                "--data-source",
                "AdventureWorks",
                "--schema",
                "Sales",
                "--table",
                "Customer",
                "--json",
            ],
            solution_path,
        )
    )
    assert result["operation"] == "import-external"
    entity = _show(target, solution_path)
    assert entity["sources"][0]["dataSource"] == "AdventureWorks"
    assert entity["sources"][0]["sourceLocation"] == "[Sales].[Customer]"
    assert [attr["name"] for attr in entity["attributes"]] == ["CustomerID", "Name"]


@pytest.mark.parametrize(
    "args",
    [
        ["entities", "patch", "modelEntities/020-Core/Missing", "--set", "description=x", "--json"],
        [
            "entities",
            "move",
            "modelEntities/020-Core/Missing",
            "modelEntities/020-Core/Other",
            "--json",
        ],
    ],
)
def test_expected_json_errors_do_not_print_tracebacks(
    args: list[str], tmp_path: Path, config: DataM8TestConfig
) -> None:
    solution_path = _copy_solution(tmp_path, config)
    result = _run(args, solution_path)
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert "Traceback" not in result.output
