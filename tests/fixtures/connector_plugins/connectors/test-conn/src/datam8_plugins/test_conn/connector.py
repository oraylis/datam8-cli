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

from typing import Any


class Connector:
    @staticmethod
    def get_manifest() -> dict[str, Any]:
        return {
            "id": "test-conn",
            "displayName": "Test Connector",
            "version": "0.1.0",
            "capabilities": ["uiSchema", "validateConnection", "metadata"],
        }

    @staticmethod
    def get_ui_schema() -> dict[str, Any]:
        return {
            "title": "Test connector connection",
            "authModes": [
                {
                    "id": "basic",
                    "label": "Basic",
                    "fields": [
                        {"key": "auth.mode", "label": "Authentication", "type": "hidden", "required": True, "default": "basic"},
                        {"key": "host", "label": "Host", "type": "string", "required": True},
                        {"key": "password", "label": "Password", "type": "secret", "required": True, "secret": True},
                    ],
                }
            ],
        }

    @staticmethod
    def validate_connection(extended_properties: dict[str, str], secret_resolver) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        if not (extended_properties.get("host") or "").strip():
            errors.append({"key": "host", "message": "Host is required.", "level": "error"})
        if not (extended_properties.get("password") or "").strip():
            errors.append({"key": "password", "message": "Password is required.", "level": "error"})
        return errors

    @staticmethod
    def test_connection(extended_properties: dict[str, str], secret_resolver) -> None:
        _ = secret_resolver.resolve(key="password", value=extended_properties.get("password") or "")
        return None

    @staticmethod
    def list_schemas(extended_properties: dict[str, str], secret_resolver) -> list[str]:
        return ["public"]

    @staticmethod
    def list_tables(extended_properties: dict[str, str], secret_resolver, schema: str | None = None) -> list[dict[str, Any]]:
        _ = schema
        return [{"schema": "public", "name": "t1", "type": "BASE TABLE"}]

    @staticmethod
    def get_table_metadata(extended_properties: dict[str, str], secret_resolver, schema: str, table: str) -> dict[str, Any]:
        return {"schema": schema, "name": table, "type": "BASE TABLE", "columns": [{"name": "id", "dataType": "int"}]}

