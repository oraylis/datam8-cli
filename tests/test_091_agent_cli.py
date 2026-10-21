"""Exercise the public CLI against disposable, self-contained solutions."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_016_base_creation import BASE_ITEMS
from typer.testing import CliRunner

from datam8 import config, factory, solution
from datam8.api.app import create_app
from datam8.app import app


@pytest.fixture
def workspace(tmp_path):
    path = tmp_path / "CLI.dm8s"
    solution.init_solution(path)
    zones = path.parent / "base/Zones.json"
    zones.write_text(
        json.dumps(
            {"type": "zones", "zones": [{"name": "Raw", "targetName": "raw", "displayName": "Raw"}]}
        )
    )
    return path


def run(workspace, *args, stdin=None, code=0):
    result = CliRunner().invoke(app, [*args, "-s", str(workspace), "--json"], input=stdin)
    assert result.exit_code == code, (result.output, result.exception)
    payload = json.loads(result.stdout)
    assert len(result.stdout.splitlines()) == 1
    assert payload["ok"] == (code == 0)
    return payload


@pytest.mark.parametrize("kind", BASE_ITEMS)
def test_base_roundtrip_selected_collection(workspace, kind):
    target = next(
        path
        for path in (workspace.parent / "base").glob("*.json")
        if json.loads(path.read_text())["type"] == kind
    )
    before = set(workspace.parent.rglob("*.json"))
    data = {**BASE_ITEMS[kind], "name": "AgentItem"}
    locator = f"{kind}/Priority/AgentItem" if kind == "propertyValues" else f"{kind}/AgentItem"
    run(
        workspace,
        "create",
        locator,
        "--source-file",
        target.relative_to(workspace.parent).as_posix(),
        "--file",
        "-",
        stdin=json.dumps(data),
    )
    assert set(workspace.parent.rglob("*.json")) == before
    run(workspace, "update", locator, "--data", '{"displayName":"Changed"}')
    assert run(workspace, "show", locator)["item"]["data"]["displayName"] == "Changed"
    run(workspace, "clone", locator, locator.replace("AgentItem", "Copy"))
    run(workspace, "rename", locator, "Renamed")
    renamed = locator.replace("AgentItem", "Renamed")
    assert any(row["name"] == "Renamed" for row in json.loads(target.read_text())[kind])
    run(workspace, "delete", renamed)
    assert run(workspace, "show", renamed, code=3)["error"]["code"] == "not_found"


def entity_data(name="Customer"):
    return {
        "name": name,
        "attributes": [
            {
                "name": "Id",
                "ordinalNumber": 1,
                "attributeType": "Regular",
                "dataType": {"type": "int", "nullable": False},
                "dateAdded": "2026-01-01T00:00:00Z",
            }
        ],
        "sources": [],
        "relationships": [],
        "transformations": [],
    }


def test_nested_updates_batch_failure_and_reload(workspace):
    locator = "modelEntities/Raw/Customer"
    run(workspace, "create", locator, "--data", json.dumps(entity_data()))
    operations = [
        {
            "op": "update",
            "locator": locator,
            "at": ["attributes", {"name": "Id"}],
            "data": {"description": "Changed"},
        },
        {
            "op": "update",
            "locator": locator,
            "at": ["attributes", {"name": "Id"}, "dataType", "nullable"],
            "data": True,
        },
        {"op": "update", "locator": locator, "data": {"id": 999}},
        {"op": "delete", "locator": locator},
    ]
    response = run(
        workspace, "apply", "--file", "-", stdin=json.dumps({"operations": operations}), code=2
    )
    assert response["failedIndex"] == 2
    assert len(response["results"]) == 2
    attribute = run(workspace, "show", locator, "--at", '["attributes",{"name":"Id"}]')["item"][
        "data"
    ]
    assert attribute["description"] == "Changed"
    assert attribute["dataType"] == {"type": "int", "nullable": True}
    assert run(workspace, "update", locator, "--at", '["attributes",{}]', "--data", "{}", code=2)
    assert run(
        workspace,
        "update",
        locator,
        "--at",
        '["attributes",{"name":"missing"}]',
        "--data",
        "{}",
        code=2,
    )
    run(
        workspace,
        "create",
        locator,
        "--at",
        '["parameters"]',
        "--data",
        '{"name":"size","value":3}',
    )
    run(workspace, "delete", locator, "--at", '["parameters",{"name":"size"}]')
    assert run(workspace, "show", locator, "--at", '["parameters"]')["item"]["data"] == []
    invalid = {
        "operations": [{"op": "delete", "locator": locator}, {"op": "update", "locator": locator}]
    }
    run(workspace, "apply", "--file", "-", stdin=json.dumps(invalid), code=2)
    assert run(workspace, "show", locator)["item"]["data"]["name"] == "Customer"


def test_function_lifecycle_and_folder_move(workspace):
    locator = "modelEntities/Raw/Customer"
    created = run(workspace, "create", locator, "--data", json.dumps(entity_data()))
    assert created["item"]["id"] > 0
    run(
        workspace,
        "functions",
        "create",
        locator,
        "--step-no",
        "1",
        "--name",
        "Clean",
        "--source",
        "clean.py",
        "--file",
        "-",
        stdin="def transform(df):\n    return df\n",
    )
    file = workspace.parent / "model/Raw/clean.py"
    run(
        workspace,
        "functions",
        "create",
        locator,
        "--step-no",
        "2",
        "--name",
        "Other",
        "--source",
        "clean.py",
        "--code",
        "overwritten",
        code=2,
    )
    run(workspace, "functions", "update", locator, "--step-no", "1", "--code", "# changed\n")
    assert file.read_text() == "# changed\n"
    run(workspace, "functions", "move", locator, "scripts/clean.py", "--name", "Clean")
    assert not file.exists()
    run(workspace, "move", locator, "modelEntities/Raw/Sub/Customer")
    locator = "modelEntities/Raw/Sub/Customer"
    assert (
        run(workspace, "functions", "show", locator, "--name", "Clean")["item"]["sourceCode"]
        == "# changed\n"
    )
    run(workspace, "functions", "move", locator, "../escape.py", "--name", "Clean", code=2)
    run(workspace, "functions", "delete", locator, "--name", "Clean")
    assert not list((workspace.parent / "model").rglob("*.py"))
    run(workspace, "create", "folders/Raw/Folder", "--data", '{"id":101}')
    assert run(workspace, "show", "folders/Raw/Folder")["item"]["data"]["path"] == "Raw/Folder"


def test_cli_and_api_updates_persist_the_same_payload(workspace):
    run(workspace, "update", "dataTypes/int", "--data", '{"displayName":"CLI"}')
    config.set_solution(workspace)
    config.lazy = True
    factory.create_model()
    client = TestClient(create_app())
    assert client.patch("/entities/dataTypes/int", json={"displayName": "API"}).status_code == 200
    assert client.post("/model/save").status_code == 204
    assert client.put("/entities/folders/Raw/ApiFolder", json={"id": 102}).status_code == 200
    assert client.post("/model/save").status_code == 204
    assert (workspace.parent / "model/Raw/ApiFolder/.properties.json").is_file()
    assert run(workspace, "show", "dataTypes/int")["item"]["data"]["displayName"] == "API"


def test_process_json_stdout_exit_codes_and_schema(workspace):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        "PYTHONIOENCODING": "cp1252",
    }
    run(workspace, "update", "dataTypes/int", "--data", json.dumps({"displayName": "Größe 中文"}))
    commands = [
        (["update", "dataTypes/int", "--file", "-", "-s", str(workspace)], 0),
        (["list", "zones", "--limit", "0", "-s", str(workspace)], 0),
        (["show", "dataTypes/absent", "-s", str(workspace)], 3),
        (["update"], 2),
        (["schema", "modelEntities", "--at", '["attributes","description"]'], 0),
        (["show", "dataTypes/int", "--fields", "displayName", "-s", str(workspace)], 0),
    ]
    for args, code in commands:
        result = subprocess.run(
            [sys.executable, "-m", "datam8", *args, "--json"],
            capture_output=True,
            input=json.dumps({"displayName": "Größe 中文"}, ensure_ascii=False)
            if "--file" in args
            else None,
            text=True,
            encoding="utf-8",
            env=env,
        )
        assert result.returncode == code, result.stderr
        assert json.loads(result.stdout)["ok"] == (code == 0)
        assert len(result.stdout.splitlines()) == 1
        if "displayName" in args:
            assert json.loads(result.stdout)["item"]["data"]["displayName"] == "Größe 中文"


def test_noninteractive_init_root_options_and_missing_solution(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAM8_SOLUTION_PATH", str(tmp_path / "environment.dm8s"))
    path = tmp_path / "new/CLI.dm8s"
    result = run(path, "init", "CLI")
    assert Path(result["item"]["solutionFile"]).is_file()
    result = CliRunner().invoke(
        app, ["-s", str(path), "solution", "show", "--json", "--fields", "basePath"]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["item"] == {"basePath": "base"}
    run(tmp_path / "absent.dm8s", "list", code=3)
    run(path, "init", "CLI", code=2)


def test_secret_stdin_batch_and_plugin_json(workspace, monkeypatch):
    from datam8 import secrets
    from datam8.cmd import secret as secret_commands

    stored = {}

    class MemorySecrets:
        def get_secret(self, path):
            return stored.get(str(path))

        def set_secret(self, path, value, force=False):
            stored[str(path)] = value

    monkeypatch.setattr(secrets, "SecretResolver", MemorySecrets)
    monkeypatch.setattr(secret_commands, "SecretResolver", MemorySecrets)
    run(workspace, "secrets", "check", "Agent/password", code=3)
    value = "private-test-value"
    receipt = run(workspace, "secrets", "set", "Agent/password", "--file", "-", stdin=value)
    assert value not in json.dumps(receipt)
    assert run(workspace, "secrets", "check", "Agent/password")["item"]["available"]
    run(
        workspace,
        "apply",
        "--file",
        "-",
        stdin=json.dumps(
            {
                "operations": [
                    {"op": "secrets.set", "path": "Agent/password", "value": value, "force": True}
                ]
            }
        ),
    )
    assert stored["Agent/password"] == value
    assert (
        run(workspace, "plugins", "show", "builtin:SQLServer")["item"]["manifest"]["id"]
        == "builtin:SQLServer"
    )


@pytest.mark.parametrize("json_output", [False, True])
def test_secret_show_is_unavailable_without_accessing_keyring(workspace, monkeypatch, json_output):
    from datam8.cmd import secret as secret_commands

    def forbidden_resolver():
        pytest.fail("Removed secret command must not access the keyring")

    monkeypatch.setattr(secret_commands, "SecretResolver", forbidden_resolver)
    args = ["secrets", "show", "Agent/password", "-s", str(workspace)]
    result = CliRunner().invoke(app, [*args, "--json"] if json_output else args, input="y\n")
    assert result.exit_code == 2, result.output
    if json_output:
        response = json.loads(result.stdout)
        assert response["ok"] is False
        assert "No such command" in response["error"]["message"]
    else:
        assert "No such command" in result.stderr


def test_ambiguous_selectors_and_shared_function_sources(workspace):
    locator = "modelEntities/Raw/Shared"
    data = entity_data("Shared")
    data["attributes"].append({**data["attributes"][0], "ordinalNumber": 2})
    run(workspace, "create", locator, "--data", json.dumps(data))
    run(
        workspace, "update", locator, "--at", '["attributes",{"name":"Id"}]', "--data", "{}", code=2
    )
    run(
        workspace,
        "functions",
        "create",
        locator,
        "--step-no",
        "1",
        "--name",
        "First",
        "--source",
        "shared.py",
        "--code",
        "# shared",
    )
    run(
        workspace,
        "create",
        locator,
        "--at",
        '["transformations"]',
        "--data",
        '{"stepNo":2,"kind":"function","name":"Second","function":{"source":"shared.py"}}',
    )
    file = workspace.parent / "model/Raw/shared.py"
    run(workspace, "functions", "delete", locator, "--step-no", "1")
    assert file.read_text() == "# shared"
    run(workspace, "functions", "delete", locator, "--step-no", "2")
    assert not file.exists()


@pytest.fixture
def generation_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "mode", config.RunMode.CLI)
    path = tmp_path / "solution/CLI.dm8s"
    solution.init_solution(path)
    descriptor = json.loads(path.read_text())
    descriptor["generatorTargets"] = [
        {"name": "test", "isDefault": True, "sourcePath": "templates", "outputPath": "output"}
    ]
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    modules = path.parent / "templates/__modules"
    modules.mkdir(parents=True)
    (modules / "payload.py").write_text(
        "from pathlib import Path\n"
        "from datam8.generate import register_payload, BasePayload\n"
        "@register_payload('test.j2')\n"
        "def cli_test_payload(model, cache):\n"
        "    return [BasePayload({'text': 'generated'}, Path('test.txt'))]\n",
        encoding="utf-8",
    )
    (path.parent / "templates/test.j2").write_text("{{ data.text }}", encoding="utf-8")
    return path


@pytest.mark.parametrize("output", ["output", "../output", "absolute"])
@pytest.mark.parametrize("mode", ["human", "json", "batch"])
def test_generate_output_paths(generation_workspace, output, mode):
    path = generation_workspace
    if output == "absolute":
        output = (path.parent.parent / "output").as_posix()
    descriptor = json.loads(path.read_text())
    descriptor["generatorTargets"][0]["outputPath"] = output
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    if mode == "batch":
        receipt = run(path, "apply", "--file", "-", stdin='{"operations":[{"op":"generate"}]}')
        receipt = receipt["results"][0]
    elif mode == "json":
        receipt = run(path, "generate")
    else:
        result = CliRunner().invoke(app, ["generate", "-s", str(path)])
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "Generation successful"
    if mode != "human":
        assert receipt["target"] == "test"
        assert receipt["outputPath"] == output
    assert (path.parent / output / "test.txt").read_text() == "generated"


@pytest.mark.parametrize("failure", ["target", "template", "module"])
@pytest.mark.parametrize("mode", ["human", "json", "batch"])
def test_generate_errors_keep_cli_output_and_batch_receipts(generation_workspace, failure, mode):
    path = generation_workspace
    target = "missing" if failure == "target" else "test"
    if failure == "template":
        (path.parent / "templates/test.j2").write_text("{{ data.missing }}", encoding="utf-8")
    if failure == "module":
        (path.parent / "templates/__modules/payload.py").write_text(
            "import datam8_review_missing_module_42\n", encoding="utf-8"
        )
    batch = {
        "operations": [
            {"op": "update", "locator": "dataTypes/int", "data": {"displayName": "Before"}},
            {"op": "generate", "target": target},
            {"op": "update", "locator": "dataTypes/int", "data": {"displayName": "After"}},
        ]
    }
    args = ["apply", "--file", "-", "--json"] if mode == "batch" else ["generate", target]
    if mode == "json":
        args.append("--json")
    result = subprocess.run(
        [sys.executable, "-m", "datam8", *args, "-s", str(path)],
        input=json.dumps(batch) if mode == "batch" else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert result.returncode == 1, result.stderr
    assert result.stderr
    if mode == "human":
        assert not result.stdout.strip()
        return
    response = json.loads(result.stdout)
    assert len(result.stdout.splitlines()) == 1
    assert response["ok"] is False
    assert response["error"]["code"] == "execution_error"
    if mode == "batch":
        assert response["failedIndex"] == 1
        assert len(response["results"]) == 1
        assert response["results"][0]["op"] == "update"
        assert run(path, "show", "dataTypes/int")["item"]["data"]["displayName"] == "Before"
