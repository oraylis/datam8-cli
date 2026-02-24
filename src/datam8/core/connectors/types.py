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

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class MetadataConnector(Protocol):
    def test_connection(self) -> dict[str, Any]: ...

    def list_schemas(self) -> list[dict[str, Any]]: ...

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]: ...

    def get_table_metadata(self, *, schema: str, table: str) -> dict[str, Any]: ...


class HttpApiConnector(Protocol):
    def request_json_array(self, *, url: str) -> list[Any]: ...


@dataclass(frozen=True)
class ConnectorModule:
    manifest: dict[str, Any]
    create_connector: Callable[[dict[str, Any], dict[str, str]], Any]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    config: dict[str, Any]
    required_secrets: list[str]
    errors: list[dict[str, str]]
