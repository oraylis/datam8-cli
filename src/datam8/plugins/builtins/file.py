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
import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from datam8 import logging, utils
from datam8.plugins import Plugin
from datam8_model.data_type import DataTypeDefinition
from datam8_model.plugin import Capability, PluginManifest

logger = logging.getLogger(__name__)

manifest_csv = PluginManifest(
    id="builtin:LocalFileCsv",
    displayName="Local CSV File (builtin)",
    version="0.1.0",
    entryPoint="datam8.plugins.builtins.file:CsvFile",
    capabilities=[
        Capability.METADATA,
        Capability.UI_SCHEMA,
        Capability.VALIDATION_CONNECTION,
    ],
)


class CsvFile(Plugin):
    def get_table_metadata(self, table: str, /, schema: str | None = None) -> Any:
        pass

    def validate_connection(self) -> Exception | None:
        self._parse_connectionstring()

    def test_connection(self) -> Exception | None:
        match self._parse_connectionstring():
            case ["file", rest]:
                if not Path(rest).exists():
                    raise utils.create_error(FileNotFoundError(f"Path '{rest}' does not exist."))
            case [unknown, *rest]:
                raise utils.create_error(f"Protocol '{unknown}' is not implemented for CsvFiles")

    def _parse_connectionstring(self) -> list[str]:
        if self._data_source.connectionString is None:
            raise utils.create_error("A connectionString must be set when connecting to files")

        if "://" not in self._data_source.connectionString:
            raise utils.create_error(
                "Connectionstring must be in the form of <protocol>://<path> or only a path"
            )

        return self._data_source.connectionString.split("://")

    def _get_paths_from_connectionstring(self) -> list[Path]:
        match self._parse_connectionstring():
            case ["file", *rest]:
                paths = list(Path(*rest).glob("*.csv"))
            case [unknown, *rest]:
                raise utils.create_error(f"Protocol '{unknown}' is not implemented for CsvFiles")

        return paths

    def list_tables(self, schema: str | None = None, /) -> list[str]:
        files = [path.as_posix() for path in self._get_paths_from_connectionstring()]
        return files

    def preview_data(
        self, table_name: str, /, schema: str | None = None, *, limit: int = 10
    ) -> list[list[str]]:
        match self._parse_connectionstring():
            case ["file", *rest]:
                path = Path(*rest) / table_name
            case [unknown, *rest]:
                raise utils.create_error(f"Protocol '{unknown}' is not implemented for CsvFiles")

        line_count = 0
        lines: list[list[str]] = []
        dialect = (self._data_source.extendedProperties or {}).get("dialect", "excel")

        with open(path) as file_:
            reader = csv.reader(file_, dialect)
            for row in reader:
                lines.append(row)
                line_count += 1
                if line_count >= limit:
                    break

        return lines

    def get_ui_schema() -> dict[str, str]:
        return {}

    @staticmethod
    def get_data_type_mappings() -> dict[str, DataTypeDefinition]:
        return {
            "string": DataTypeDefinition(name="string", targets=Mapping()),
            "number": DataTypeDefinition(name="decimal", targets=Mapping()),
        }
