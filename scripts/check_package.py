"""Exercise an installed release package outside the source checkout."""

import importlib.metadata
import importlib.resources
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


def main():
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected_version = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]["version"]
    evidence = Path(sys.argv[1]).resolve()
    fixture = Path(sys.argv[2]).resolve()
    evidence.mkdir()
    command = [sys.executable, "-m", "datam8"]
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"}
    environment.pop("PYTHONPATH", None)

    def cli(*arguments):
        return subprocess.run(
            [*command, *arguments],
            cwd=evidence,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )

    assert importlib.metadata.version("datam8") == expected_version
    assert cli("--version").stdout.strip() == expected_version
    assert "generate" in cli("--help").stdout
    cli("init", "Smoke", "--type", "empty", "--solution", str(evidence / "solution"))
    solution = evidence / "solution" / "Smoke.dm8s"

    from datam8 import config
    from datam8.plugins.manager import PluginManager
    from datam8_model.data_source import DataSource, DataSourceType

    assert Path(config.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    config.set_solution(solution)
    manager = PluginManager()
    for plugin_id in ("CsvFile", "OdcsFile", "DatabricksUnityCatalog"):
        assert manager.get_plugin(plugin_id) is manager.get_plugin(f"builtin:{plugin_id}")

    resources = importlib.resources.files("datam8.plugins.builtins") / "resources"
    schema = json.loads((resources / "odcs-json-schema-v3.2.0.json").read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    assert "Apache" in (resources / "ODCS-LICENSE.txt").read_text(encoding="utf-8")
    odcs = manager.get_plugin("builtin:OdcsFile")
    contract_file = evidence / "contract.odcs.yaml"
    shutil.copyfile(fixture, contract_file)
    source_type = DataSourceType(
        name="OdcsFile",
        pluginId=odcs.manifest().id,
        connectionProperties=odcs.get_connection_properties(),
        authModes=odcs.get_auth_modes(),
        dataTypeMapping=odcs.get_data_type_mappings(),
    )
    plugin = odcs(
        odcs.manifest(),
        DataSource(
            name="Contracts",
            type=source_type.name,
            extendedProperties={"path": str(contract_file), "protocol": "file"},
        ),
        source_type,
    )
    locations = plugin.list_source().to_dicts()
    assert locations
    fields = list(plugin.get_table_metadata(locations[0]["sourceLocation"]).iter_source_fields())
    assert fields

    output = queue.Queue()
    stdout_lines = []
    token = "release-smoke-local-only"
    with (evidence / "server-stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [
                *command,
                "serve",
                "--solution",
                str(solution),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--token",
                token,
            ],
            cwd=evidence,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
        )

        def collect():
            for line in process.stdout:
                stdout_lines.append(line)
                output.put(line)

        collector = threading.Thread(target=collect, daemon=True)
        collector.start()
        try:
            ready = json.loads(output.get(timeout=40))
            assert ready["type"] == "ready" and ready["version"] == expected_version, ready
            base_url = ready["baseUrl"]

            def request(path, auth=False):
                headers = {"Authorization": f"Bearer {token}"} if auth else {}
                with urllib.request.urlopen(
                    urllib.request.Request(base_url + path, headers=headers),
                    timeout=10,
                ) as response:
                    data = response.read()
                    return response.status, json.loads(data) if data else None

            assert request("/health") == (204, None)
            assert request("/version")[1]["appVersion"] == expected_version
            assert request("/solution", auth=True)[0] == 200
            try:
                request("/solution")
                raise AssertionError("Protected endpoint accepted a request without a token")
            except urllib.error.HTTPError as error:
                assert error.code == 401
        finally:
            process.terminate()
            process.wait(timeout=10)
            collector.join(timeout=5)
            (evidence / "server-stdout.log").write_text("".join(stdout_lines), encoding="utf-8")
    assert len(stdout_lines) == 1, stdout_lines
    print(
        json.dumps(
            {
                "version": expected_version,
                "installed_module": str(importlib.resources.files("datam8")),
                "odcs_objects": len(locations),
                "odcs_fields": len(fields),
                "checks": [
                    "cli-version",
                    "cli-help",
                    "blank-init",
                    "builtin-aliases",
                    "bundled-schema-license",
                    "offline-odcs-metadata",
                    "api-ready",
                    "health",
                    "version",
                    "authorized-solution",
                    "unauthorized-401",
                    "single-stdout-readiness-line",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
