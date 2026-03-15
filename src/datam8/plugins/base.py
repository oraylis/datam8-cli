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

from abc import ABC, abstractmethod
from typing import Any

from datam8_model.data_source import DataSource
from datam8_model.plugin import Capability, PluginManifest

VALIDATION_CONNECTION = Capability.VALIDATION_CONNECTION
METADATA = Capability.METADATA
UI_SCHEMA = Capability.UI_SCHEMA


class Plugin(ABC):
    def __init__(
        self,
        manifest: PluginManifest,
        /,
        data_source: DataSource,
    ) -> None:
        self.__manifest = manifest
        self.__data_source = data_source
        self.__type = type

    def is_capable_of(self, capability: Capability, /) -> bool:
        return capability in self.__manifest.capabilities

    def get_manifest(self) -> PluginManifest:
        return self.__manifest

    def validate_connection(self) -> Exception | None:
        if not self.is_capable_of(VALIDATION_CONNECTION):
            return

    def test_connection(self) -> Exception | None:
        if not self.is_capable_of(VALIDATION_CONNECTION):
            return

    def list_schemas(self) -> Any:
        if not self.is_capable_of(METADATA):
            return

    def list_tables(self, schema: str, /) -> Any:
        if not self.is_capable_of(METADATA):
            return

    def get_table_metadata(self, table: str, /, schema: str | None = None) -> Any:
        if not self.is_capable_of(METADATA):
            return

    @abstractmethod
    def get_ui_schema(self) -> Any: ...
