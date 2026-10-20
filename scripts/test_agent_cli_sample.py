"""Opt-in CLI acceptance against a disposable sample copy and its real source."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--data-source", default="AdventureWorks")
    parser.add_argument("--schema", default="SalesLT")
    parser.add_argument("--object", default="Address")
    parser.add_argument("--zone", default="raw")
    args = parser.parse_args()
    checks = []
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    source_path = args.solution.resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="datam8-cli-acceptance-") as temporary:
        directory = (Path(temporary) / "solution").resolve()
        shutil.copytree(
            source_path.parent, directory, ignore=shutil.ignore_patterns(".git", "__pycache__")
        )
        solution_path = directory / source_path.name
        descriptor = json.loads(solution_path.read_text(encoding="utf-8"))
        paths = [descriptor[key] for key in ("basePath", "modelPath", "pluginsPath")]
        paths.extend(
            target[key]
            for target in descriptor["generatorTargets"]
            for key in ("sourcePath", "outputPath")
        )
        if any(not (directory / path).resolve().is_relative_to(directory) for path in paths):
            raise ValueError("Sample paths must stay inside the disposable solution copy")
        previewed = 0

        def run(label, *command, stdin=None, expected=0):
            result = subprocess.run(
                [sys.executable, "-m", "datam8", *command, "-s", str(solution_path), "--json"],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=120,
            )
            try:
                value = json.loads(result.stdout)
            except ValueError:
                raise AssertionError(f"{label}: stdout is not one JSON document") from None
            check = {
                "check": label,
                "exitCode": result.returncode,
                "passed": result.returncode == expected,
            }
            checks.append(check)
            print(json.dumps(check), flush=True)
            if result.returncode != expected:
                raise AssertionError(
                    f"{label}: {value.get('error', {}).get('code', 'unexpected exit')}"
                )
            return value

        try:
            for target in ("docs", "databricks"):
                run(f"baseline generate {target}", "generate", target)
            run("baseline validate", "validate")
            run("source connection", "sources", "test-connection", args.data_source)
            run("source capabilities", "sources", "capabilities", args.data_source)
            run("source root navigation", "sources", "list", args.data_source)
            objects = run(
                "source schema navigation",
                "sources",
                "list",
                args.data_source,
                "--source-location",
                args.schema,
            )["items"]
            location = next(row["sourceLocation"] for row in objects if row["name"] == args.object)
            metadata = run("source metadata", "sources", "metadata", args.data_source, location)
            assert metadata["count"] > 0
            preview = run(
                "source preview", "sources", "preview", args.data_source, location, "--limit", "10"
            )
            assert 0 < preview["count"] <= 10
            previewed = preview["count"]
            run(
                "source import description",
                "sources",
                "import-description",
                args.data_source,
                location,
            )

            def create(label, locator, data, *extra):
                return run(label, "create", locator, "--data", json.dumps(data), *extra)

            base = Path(descriptor["basePath"])
            collections = {
                json.loads(path.read_text(encoding="utf-8"))["type"]: path.relative_to(
                    directory
                ).as_posix()
                for path in (directory / base).rglob("*.json")
            }
            base_files = set((directory / base).rglob("*.json"))
            create(
                "selected Base data type",
                "dataTypes/AgentCliType",
                {"targets": {"databricks": "string", "powerbi": "string"}},
                "--source-file",
                collections["dataTypes"],
            )
            create(
                "selected Base property",
                "properties/AgentCliTag",
                {"displayName": "Agent CLI tag", "scopes": [{"type": "entity"}]},
                "--source-file",
                collections["properties"],
            )
            create(
                "selected Base value",
                "propertyValues/AgentCliTag/Active",
                {"property": "AgentCliTag"},
                "--source-file",
                collections["propertyValues"],
            )
            assert set((directory / base).rglob("*.json")) == base_files
            product = "AgentCliProduct"
            create(
                "data product",
                f"dataProducts/{product}",
                {"dataModules": [{"name": "AgentModule"}]},
                "--source-file",
                collections["dataProducts"],
            )
            run(
                "nested data module",
                "update",
                f"dataProducts/{product}",
                "--at",
                '["dataModules",{"name":"AgentModule"}]',
                "--data",
                '{"description":"CLI acceptance"}',
            )
            folder = f"{args.zone}/{product}/AgentModule"
            create(
                "folder metadata",
                f"folders/{folder}",
                {"id": 100000001, "dataProduct": product, "dataModule": "AgentModule"},
            )

            locator = f"modelEntities/{args.zone}/AgentCliAddress"
            run("source import", "sources", "import", args.data_source, location, locator)
            imported = run("reload imported entity", "show", locator)["item"]["data"]
            assert len(imported["attributes"]) == metadata["count"]
            attribute = imported["attributes"][0]["name"]
            at = ["attributes", {"name": attribute}]
            happy = {
                "operations": [
                    {
                        "op": "update",
                        "locator": locator,
                        "at": at,
                        "data": {
                            "displayName": "Agent attribute",
                            "description": "Local description",
                        },
                    },
                    {
                        "op": "create",
                        "locator": locator,
                        "at": ["properties"],
                        "data": {"property": "AgentCliTag", "value": "Active"},
                    },
                ]
            }
            run("dependent batch", "apply", "--file", "-", stdin=json.dumps(happy))
            run("source compare", "sources", "compare", locator)
            run(
                "source-only refresh",
                "sources",
                "refresh",
                locator,
                "--mode",
                "sources-only",
                "--yes",
            )
            assert (
                run(
                    "source-only preserves local metadata", "show", locator, "--at", json.dumps(at)
                )["item"]["data"]["description"]
                == "Local description"
            )
            run("complete refresh", "sources", "refresh", locator, "--yes")
            assert (
                run("complete preserves display name", "show", locator, "--at", json.dumps(at))[
                    "item"
                ]["data"]["displayName"]
                == "Agent attribute"
            )
            clone = f"modelEntities/{folder}/AgentClone"
            run("clone", "clone", locator, clone)
            run("folder move", "move", f"modelEntities/{folder}/", f"modelEntities/{folder}Moved/")
            run("reload moved folder", "show", f"folders/{folder}Moved")
            run(
                "rename clone",
                "rename",
                clone.replace("AgentModule/", "AgentModuleMoved/"),
                "AgentRenamedClone",
            )
            run(
                "function create",
                "functions",
                "create",
                locator,
                "--step-no",
                "1",
                "--name",
                "AgentFunction",
                "--source",
                "agent_function.py",
                "--file",
                "-",
                stdin="def transform(df):\n    return df\n",
            )
            run(
                "function update",
                "functions",
                "update",
                locator,
                "--step-no",
                "1",
                "--code",
                "def transform(df):\n    return df  # CLI acceptance\n",
            )
            run(
                "function move",
                "functions",
                "move",
                locator,
                "scripts/agent_function.py",
                "--step-no",
                "1",
            )
            run("entity rename with function", "rename", locator, "AgentCliRenamedAddress")
            locator = locator.replace("AgentCliAddress", "AgentCliRenamedAddress")
            assert (
                "CLI acceptance"
                in run("reload function", "functions", "show", locator, "--step-no", "1")["item"][
                    "sourceCode"
                ]
            )
            failing = {
                "operations": [
                    {"op": "update", "locator": locator, "data": {"description": "Batch survived"}},
                    {"op": "update", "locator": locator, "data": {"id": -1}},
                    {"op": "delete", "locator": locator},
                ]
            }
            result = run(
                "batch stops after failure",
                "apply",
                "--file",
                "-",
                stdin=json.dumps(failing),
                expected=2,
            )
            assert result["failedIndex"] == 1 and len(result["results"]) == 1
            assert (
                run("reload completed batch change", "show", locator)["item"]["data"]["description"]
                == "Batch survived"
            )
            run("function delete", "functions", "delete", locator, "--step-no", "1")
            run("final validate", "validate")
            generation = run(
                "generate both targets in one batch",
                "apply",
                "--file",
                "-",
                stdin=json.dumps(
                    {
                        "operations": [
                            {"op": "generate", "target": "docs", "cleanOutput": True},
                            {"op": "generate", "target": "databricks", "cleanOutput": True},
                        ]
                    }
                ),
            )
            for generated in generation["results"]:
                output = directory / generated["outputPath"]
                assert any(path.is_file() and path.stat().st_size for path in output.rglob("*"))
            return 0
        finally:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(
                    {
                        "checks": checks,
                        "source": args.data_source,
                        "sourceRowsPreviewed": previewed,
                        "originalSolutionModified": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )


if __name__ == "__main__":
    sys.exit(main())
