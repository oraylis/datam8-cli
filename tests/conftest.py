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
import os
import pathlib

import pytest
from config import DataM8TestConfig
from pytest_cases import fixture

from datam8 import config as datam8_config
from datam8 import migration_v1, parser_v1
from datam8 import model as datam8_model
from datam8.parser import parse_full_solution_async

solution_file_path_key = pytest.StashKey[pathlib.Path]()
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
    datam8_config.mode = datam8_config.RunMode.TEST

    solution_file_path = __get_variable(config, "solution-path", None)
    log_level = __get_variable(config, "log-level", "info")

    config.stash[solution_file_path_key] = pathlib.Path(solution_file_path.replace("\\", "/"))
    config.stash[log_level_key] = log_level


@fixture
def config(request: pytest.FixtureRequest) -> DataM8TestConfig:
    """DataM8 Solution configuration."""

    datam8_config.lazy = True

    return DataM8TestConfig(
        solution_file_path=request.config.stash[solution_file_path_key],
        log_level=request.config.stash[log_level_key],
        pytest_config=request.config,
    )


@fixture
def model_lazy(config: DataM8TestConfig) -> datam8_model.Model:
    "Initialized Model object."
    datam8_config.set_solution(config.solution_file_path)
    model = asyncio.run(parse_full_solution_async(datam8_config.solution_path))
    return model


@fixture
def model(config: DataM8TestConfig) -> datam8_model.Model:
    "Initialized a lazy Model object."
    datam8_config.set_solution(config.solution_file_path)
    model = asyncio.run(parse_full_solution_async(datam8_config.solution_path))

    model.resolve()

    return model


@fixture
def migration(config: DataM8TestConfig) -> migration_v1.MigrationV1:
    return migration_v1.MigrationV1(
        {
            "/core/sales/customer/customer": parser_v1.ModelFileReference(
                id=1,
                path=pathlib.Path().cwd()
                / "tests"
                / "test_040_migration"
                / "core_entity_before.json",
            ),
            "/010-stage/sales/customer/customer": parser_v1.ModelFileReference(
                id=2, path=pathlib.Path().cwd()
            ),
            "/010-stage/sales/customer/customer_en": parser_v1.ModelFileReference(
                id=3, path=pathlib.Path().cwd()
            ),
        }
    )


def __get_variable(config: pytest.Config, variable: str, default: str | None = None) -> str:
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


@pytest.fixture
def builtin_environment(monkeypatch, tmp_path):
    """Isolate builtin tests from the configured sample and the user's keyring."""
    import datam8.secrets as secrets
    from datam8 import factory
    from datam8.plugins.builtins.databricks_uc import DatabricksUnityCatalog
    from datam8.secrets import SecretResolver

    store = {}
    monkeypatch.setattr(secrets.keyring, "get_keyring", lambda: None)
    monkeypatch.setattr(
        secrets.keyring, "get_password", lambda service, user: store.get((service, user))
    )
    monkeypatch.setattr(
        secrets.keyring,
        "set_password",
        lambda service, user, value: store.__setitem__((service, user), value),
    )
    monkeypatch.setattr(
        secrets.keyring, "delete_password", lambda service, user: store.pop((service, user), None)
    )
    monkeypatch.setattr(datam8_config, "solution_path", tmp_path / "Builtin.dm8s", raising=False)
    monkeypatch.setattr(datam8_config, "solution_folder_path", tmp_path, raising=False)
    monkeypatch.setattr(datam8_config, "mode", datam8_config.RunMode.TEST)
    monkeypatch.setattr(factory, "_model", None)
    monkeypatch.setattr(factory, "_plugin_manager", None)
    monkeypatch.setattr(secrets.os, "getlogin", lambda: "builtin-tests")
    SecretResolver.reset_singleton()
    DatabricksUnityCatalog._tokens.clear()
    yield
    DatabricksUnityCatalog._tokens.clear()
    SecretResolver.reset_singleton()


@pytest.fixture
def builtin_plugin(builtin_environment):
    from datam8_model.data_source import DataSource, DataSourceType

    def make(cls, properties, name="Builtin"):
        source_type = DataSourceType(
            name=cls.__name__,
            pluginId=cls.manifest().id,
            connectionProperties=cls.get_connection_properties(),
            authModes=cls.get_auth_modes(),
            dataTypeMapping=cls.get_data_type_mappings(),
        )
        return cls(
            cls.manifest(),
            DataSource(name=name, type=source_type.name, extendedProperties=properties),
            source_type,
        )

    return make


@pytest.fixture
def workspace():
    from builtin_plugins.mock_workspace import MockWorkspace

    with MockWorkspace() as server:
        yield server


@pytest.fixture
def make_plugin(workspace, builtin_plugin):
    from datam8.plugins.builtins.databricks_uc import DatabricksUnityCatalog
    from datam8.secrets import SecretResolver

    def make(mode="pat", **changes):
        properties = {
            "workspace_url": workspace.url,
            "authMode": mode,
            "warehouse_id": "warehouse1",
        }
        secret_key = "token" if mode == "pat" else "client_secret"
        SecretResolver().set_secret(
            f"datasources/UC/{secret_key}",
            "developer-pat" if mode == "pat" else "client-secret",
            force=True,
        )
        properties[secret_key] = f"ref://datasources/UC/{secret_key}"
        if mode != "pat":
            properties["client_id"] = "client-id"
        if mode == "azureServicePrincipal":
            properties["tenant_id"] = "tenant-id"
        properties.update(changes)
        return builtin_plugin(DatabricksUnityCatalog, properties, name="UC")

    return make
