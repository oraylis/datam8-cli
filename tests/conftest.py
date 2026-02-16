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

import asyncio
import contextlib
import dataclasses
import os
import pathlib
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pytest_cases import fixture

from datam8 import config as datam8_config
from datam8 import migration_v1, parser_v1
from datam8 import model as datam8_model
from datam8.api.app import create_app
from datam8.parser import parse_full_solution_async

solution_file_path_key = pytest.StashKey[pathlib.Path | None]()
log_level_key = pytest.StashKey[str]()


# Set Input Parameter für test
def pytest_addoption(parser):
    parser.addoption(
        "--target",
        action="store",
        help="Set the target architecture for your test",
    )
    parser.addoption(
        "--solution-path",
        action="store",
        help="Path to the dm8s solution file",
    )


def pytest_configure(config: pytest.Config):
    """Pre run."""
    # Workaround: on some dev environments TMP/TEMP can point to a Windows path under /mnt/c,
    # which breaks pytest's capture tempfiles. Force a Linux temp dir for the test session.
    for k in ("TMPDIR", "TMP", "TEMP"):
        os.environ[k] = "/tmp"
    tempfile.tempdir = "/tmp"

    solution_file_path = __get_variable(config, "solution-path", None)
    log_level = __get_variable(config, "log-level", "info")

    config.stash[solution_file_path_key] = (
        pathlib.Path(solution_file_path.replace("\\", "/")) if solution_file_path else None
    )
    config.stash[log_level_key] = log_level


@dataclasses.dataclass
class TestConfig:
    solution_file_path: pathlib.Path
    log_level: str
    pytest_config: pytest.Config


@fixture
def solution_file_path(request: pytest.FixtureRequest) -> pathlib.Path:
    configured_path = request.config.stash[solution_file_path_key]

    if configured_path is None:
        pytest.skip(
            "Set --solution-path (or DATAM8_SOLUTION_PATH) to run solution-dependent tests."
        )

    if configured_path.is_file() and configured_path.suffix.lower() == ".dm8s":
        return configured_path

    if configured_path.is_dir():
        dm8s_files = sorted(configured_path.glob("*.dm8s"))
        if len(dm8s_files) == 1:
            return dm8s_files[0]
        pytest.fail(
            f"Expected exactly one .dm8s file in {configured_path}, found {len(dm8s_files)}."
        )

    pytest.fail(
        f"DATAM8_SOLUTION_PATH/--solution-path points to a missing or invalid path: {configured_path}"
    )
    raise AssertionError("unreachable")


@fixture
def config(request: pytest.FixtureRequest, solution_file_path: pathlib.Path) -> TestConfig:
    """DataM8 Solution configuration."""

    datam8_config.lazy = True

    return TestConfig(
        solution_file_path=solution_file_path,
        log_level=request.config.stash[log_level_key],
        pytest_config=request.config,
    )


@fixture
def model_lazy(config: TestConfig) -> datam8_model.Model:
    "Initialized Model object."

    datam8_config.solution_folder_path = config.solution_file_path.parent
    model = asyncio.run(parse_full_solution_async(config.solution_file_path))
    return model


@fixture
def model(config: TestConfig) -> datam8_model.Model:
    "Initialized a lazy Model object."

    datam8_config.solution_folder_path = config.solution_file_path.parent
    model = asyncio.run(parse_full_solution_async(config.solution_file_path))

    model.resolve()

    return model


@fixture
def migration(config: TestConfig) -> migration_v1.MigrationV1:
    return migration_v1.MigrationV1(
        {
            "/Core/Sales/Customer/Customer": parser_v1.ModelFileReference(
                id=1,
                path=pathlib.Path().cwd()
                / "tests"
                / "test_040_migration"
                / "core_entity_before.json",
            ),
            "/010-Stage/Sales/Customer/Customer": parser_v1.ModelFileReference(
                id=2, path=pathlib.Path().cwd()
            ),
            "/010-Stage/Sales/Customer/Customer_EN": parser_v1.ModelFileReference(
                id=3, path=pathlib.Path().cwd()
            ),
        }
    )


@fixture(scope="session")
def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


@fixture(scope="session")
def fixture_connector_plugins_dir(repo_root: pathlib.Path) -> pathlib.Path:
    path = repo_root / "tests" / "fixtures" / "connector_plugins"
    if not path.exists():
        raise RuntimeError(f"Missing fixture at {path}")
    return path


@fixture(scope="session")
def fixture_job_solution_dir(repo_root: pathlib.Path) -> pathlib.Path:
    path = repo_root / "tests" / "fixtures" / "job_solution"
    if not path.exists():
        raise RuntimeError(f"Missing fixture at {path}")
    return path


@fixture
def temp_plugin_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


@fixture
def api_client():
    @contextlib.contextmanager
    def _factory(
        *,
        token: str,
        plugin_dir: pathlib.Path | None = None,
        solution_path: pathlib.Path | None = None,
    ) -> Iterator[TestClient]:
        previous_tempdir = tempfile.tempdir
        previous = {
            "DATAM8_PLUGIN_DIR": os.environ.get("DATAM8_PLUGIN_DIR"),
            "DATAM8_SOLUTION_PATH": os.environ.get("DATAM8_SOLUTION_PATH"),
            "TMPDIR": os.environ.get("TMPDIR"),
            "TMP": os.environ.get("TMP"),
            "TEMP": os.environ.get("TEMP"),
        }

        if plugin_dir is not None:
            os.environ["DATAM8_PLUGIN_DIR"] = str(plugin_dir)
        if solution_path is not None:
            os.environ["DATAM8_SOLUTION_PATH"] = str(solution_path)

        if plugin_dir is not None:
            temp_root = str(plugin_dir.parent)
            os.environ["TMPDIR"] = temp_root
            os.environ["TMP"] = temp_root
            os.environ["TEMP"] = temp_root
            tempfile.tempdir = temp_root

        try:
            app = create_app(token=token, enable_openapi=False)
            with TestClient(app) as client:
                yield client
        finally:
            tempfile.tempdir = previous_tempdir
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return _factory


def __get_variable(
    config: pytest.Config, variable: str, default: str | None = None
) -> str:
    variable_from_env = __get_variable_from_env(variable)
    variable_from_cli = __get_variable_from_cli(config, variable)

    result = variable_from_cli or variable_from_env or default

    return result or ""


def __get_variable_from_env(var: str) -> str | None:
    variable_name = f"DATAM8_{var.upper().replace('-', '_')}"

    if variable_name in os.environ:
        return os.environ[variable_name]
    else:
        return None


def __get_variable_from_cli(config: pytest.Config, var: str) -> str | None:
    return config.getoption(f"--{var}")


