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
import dataclasses
import os
import pathlib
import tempfile

import pytest
from pytest_cases import fixture

from datam8 import config as datam8_config
from datam8 import model as datam8_model
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
def config(request: pytest.FixtureRequest) -> TestConfig:
    """DataM8 Solution configuration."""

    datam8_config.lazy = True

    solution_path = request.config.stash[solution_file_path_key]
    if solution_path is None:
        pytest.skip("Set --solution-path (or DATAM8_SOLUTION_PATH) to run model-centric tests.")

    return TestConfig(
        solution_file_path=solution_path,
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
