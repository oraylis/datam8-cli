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

import vendored_dep


class Connector:
    @staticmethod
    def get_manifest() -> dict:
        return {
            "id": "testdep",
            "displayName": "Testdep",
            "version": vendored_dep.VALUE,
            "capabilities": ["uiSchema", "validateConnection", "metadata"],
        }

    @staticmethod
    def get_ui_schema() -> dict:
        return {"title": "Testdep", "authModes": [{"id": "none", "label": "None", "fields": []}]}

    @staticmethod
    def validate_connection(extended_properties: dict, secret_resolver) -> list:
        return []

    @staticmethod
    def test_connection(extended_properties: dict, secret_resolver) -> None:
        return None

    @staticmethod
    def list_schemas(extended_properties: dict, secret_resolver) -> list[str]:
        return []

    @staticmethod
    def list_tables(
        extended_properties: dict,
        secret_resolver,
        schema: str | None = None,
    ) -> list[dict]:
        return []

    @staticmethod
    def get_table_metadata(extended_properties: dict, secret_resolver, schema: str, table: str) -> dict:
        return {"schema": schema, "name": table, "columns": []}
