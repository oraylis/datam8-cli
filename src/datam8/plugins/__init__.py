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

from .base import Plugin, TableMetadata
from .builtins.file import CsvFile
from .manager import PluginManager

__all__ = [
    "Plugin",
    "TableMetadata",
    "init_builtin_plugins",
]

PluginManager.register_builtin_plugin("builtin:CsvFile", CsvFile.manifest())


# the AzureDataLake and SQLServer plugins require additional extra dependencies to be installed, so
# they are lazyly loaded


def register_lake_source() -> None:
    from .builtins.lake_source import AzureDataLake

    PluginManager.register_builtin_plugin("builtin:AzureDataLake", AzureDataLake.manifest())


def register_sql_server() -> None:
    from .builtins.sql_server import SqlServer

    PluginManager.register_builtin_plugin("builtin:SQLServer", SqlServer.manifest())


def init_builtin_plugins(
    *, plugin_id: str | None = None
) -> None:
    match plugin_id:
        case "builtin:AzureDataLake":
            register_lake_source()

        case "builtin:SQLServer":
            register_sql_server()

        case None:
            register_lake_source()
            register_sql_server()
