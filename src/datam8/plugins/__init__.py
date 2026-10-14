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

from importlib.util import find_spec

from .base import Plugin, TableMetadata
from .builtins.databricks_uc import DatabricksUnityCatalog
from .builtins.file import CsvFile
from .builtins.odcs import OdcsFile
from .manager import PluginManager

__all__ = [
    "Plugin",
    "TableMetadata",
    "init_builtin_plugins",
]

PluginManager.register_builtin_plugin("builtin:CsvFile", CsvFile.manifest())
PluginManager.register_builtin_plugin("builtin:OdcsFile", OdcsFile.manifest())
PluginManager.register_builtin_plugin(
    "builtin:DatabricksUnityCatalog", DatabricksUnityCatalog.manifest()
)


# the AzureDataLake and SQLServer plugins require additional extra dependencies to be installed, so
# they are lazyly loaded


def register_lake_source() -> None:
    from .builtins.lake_source import AzureDataLake

    PluginManager.register_builtin_plugin("builtin:AzureDataLake", AzureDataLake.manifest())


def register_sql_server() -> None:
    from .builtins.sql_server import SqlServer

    PluginManager.register_builtin_plugin("builtin:SQLServer", SqlServer.manifest())


def _module_available(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def init_builtin_plugins(*, plugin_id: str | None = None) -> None:
    """Discover installed builtins; explicit bindings still require their extras."""
    selected = plugin_id.removeprefix("builtin:") if plugin_id is not None else None
    if selected == "AzureDataLake" or (
        selected is None
        and _module_available("azure.identity")
        and _module_available("azure.storage.filedatalake")
    ):
        register_lake_source()
    if selected == "SQLServer" or (selected is None and _module_available("connectorx")):
        register_sql_server()
