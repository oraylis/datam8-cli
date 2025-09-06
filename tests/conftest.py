import asyncio
import dataclasses
import os
import pathlib

from pytest_cases import fixture

from dm8gen import config as dm8gen_config
from dm8gen.model import Model
from dm8gen.parser import parse_full_solution_async


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


def pytest_configure(config: "TestConfig"):
    """Pre run."""
    solution_file_path = __get_variable(config, "solution-path")
    log_level = __get_variable(config, "log-level", "info")

    config.solution_file_path = pathlib.Path(
        solution_file_path.replace("\\", "/")
    )
    config.log_level = log_level


@dataclasses.dataclass
class TestConfig:
    solution_file_path: pathlib.Path
    log_level: str


@fixture
def config(request) -> TestConfig:
    """DataM8 Solution configuration."""

    return TestConfig(
        solution_file_path=request.config.solution_file_path,
        log_level=request.config.log_level,
    )


@fixture
def model(config: TestConfig) -> Model:
    """Initialized Model object."""

    dm8gen_config.solution_folder_path = config.solution_file_path.parent
    return asyncio.run(parse_full_solution_async(config.solution_file_path))


def __get_variable(
    config: TestConfig, variable: str, default: str | None = None
) -> str:
    variable_from_env = __get_variable_from_env(variable)
    variable_from_cli = __get_variable_from_cli(config, variable)

    result = variable_from_cli or variable_from_env or default

    if not result:
        raise Exception(f"No value could be set for {variable}")

    return result


def __get_variable_from_env(var: str) -> str | None:
    variable_name = f"DATAM8_{var.upper().replace('-', '_')}"

    if variable_name in os.environ:
        return os.environ[variable_name]
    else:
        return None


def __get_variable_from_cli(config: TestConfig, var: str) -> str | None:
    return config.getoption(f"--{var}")
