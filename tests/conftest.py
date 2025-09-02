from pytest_cases import fixture
from typing import Union
import os
import dataclasses

from dm8gen.Factory import Model


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
        help="Folder path to the solution",
    )


def pytest_configure(config):
    """Pre run."""
    config.target  = __get_variable(config, "target", "databricks-lake")
    config.solution_path  = __get_variable(config, "solution-path")
    config.log_level = __get_variable(config, "log-level", "INFO")

    if not config.solution_path:
        raise Exception("Solution path not set.")

    config.solution_path = config.solution_path.replace("\\", "/")
    config.solution_file_path = "%s/ORAYLISDatabricksSample.dm8s" % config.solution_path
    config.generate_path = "%s/Generate" % config.solution_path

    # stage paths
    config.source_path_stage = "%s/__models/stage.jinja2" % config.generate_path
    config.target_path_stage = "%s/Staging" % config.solution_path

    # output paths
    config.source_path_output = "%s/%s" % (config.generate_path, config.target)
    config.target_path_output = "%s/Output" % config.solution_path

    # curated paths
    config.source_path_curated = "%s/__models/curated_function.py.jinja2" % config.generate_path
    config.target_path_curated = "%s/Functions" % config.solution_path

    model = Model(config.solution_file_path, config.log_level)
    model.validate_index(full_index_scan=True)


@dataclasses.dataclass
class TestConfig:
    solution_path: str
    solution_file_path: str
    source_path_stage: str
    source_path_output: str
    source_path_curated: str
    target_path_stage: str
    target_path_output: str
    target_path_curated: str
    generate_path: str
    modules_path: str
    collections_path: str
    log_level: str


@fixture
def config(request) -> TestConfig:
    """DataM8 Solution configuration."""

    return TestConfig(
        solution_path= request.config.solution_path,
        solution_file_path= request.config.solution_file_path,
        source_path_stage= request.config.source_path_stage,
        source_path_output= request.config.source_path_output,
        source_path_curated= request.config.source_path_curated,
        target_path_stage= request.config.target_path_stage,
        target_path_output= request.config.target_path_output,
        target_path_curated= request.config.target_path_curated,
        generate_path= request.config.generate_path,
        modules_path= "%s/%s/__modules"
        % (
            request.config.generate_path,
            request.config.target,
        ),
        collections_path= "%s/__collections" % request.config.source_path_output,
        log_level= request.config.log_level,
        )


@fixture
def model(config: TestConfig) -> Model:
    """Initialized Model object."""
    model = Model(
        path_solution=config.solution_file_path, log_level=config.log_level
    )
    # model.validate_index(full_index_scan=True)
    return model


def __get_variable(config, variable: str, default: str | None = None) -> str | None:
    variable_from_env = __get_variable_from_env(variable)
    variable_from_cli = __get_variable_from_cli(config, variable)

    return variable_from_cli or variable_from_env or default


def __get_variable_from_env(var: str) -> Union[str, None]:
    variable_name = "DATAM8_%s" % var.upper().replace("-", "_")

    if variable_name in os.environ:
        return os.environ[variable_name]
    else:
        return None


def __get_variable_from_cli(config, var: str) -> Union[str, None]:
    return config.getoption("--%s" % var)
