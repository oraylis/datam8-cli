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

from typing import Any

from datam8.plugins import Plugin
from datam8.secrets import SecretResolver
from datam8_model.plugin import Capability, PluginManifest

manifest = PluginManifest(
    id="builtin:SQLServer",
    displayName="SQL Server (built-in)",
    version="0.1.0",
    entryPoint="datam8.plugins.sql_server:SqlServer",
    capabilities=[
        Capability.METADATA,
        Capability.UI_SCHEMA,
        Capability.VALIDATION_CONNECTION,
    ],
)

DATA_TYPE_MAPPING = [
    {"sourceType": "bigint", "targetType": "long"},
    {"sourceType": "binary", "targetType": "string"},
    {"sourceType": "bit", "targetType": "boolean"},
    {"sourceType": "char", "targetType": "string"},
    {"sourceType": "date", "targetType": "datetime"},
    {"sourceType": "datetime", "targetType": "datetime"},
    {"sourceType": "datetime2", "targetType": "datetime"},
    {"sourceType": "datetimeoffset", "targetType": "datetime"},
    {"sourceType": "decimal", "targetType": "decimal"},
    {"sourceType": "float", "targetType": "double"},
    {"sourceType": "image", "targetType": "string"},
    {"sourceType": "int", "targetType": "int"},
    {"sourceType": "money", "targetType": "decimal"},
    {"sourceType": "nchar", "targetType": "string"},
    {"sourceType": "ntext", "targetType": "string"},
    {"sourceType": "numeric", "targetType": "decimal"},
    {"sourceType": "nvarchar", "targetType": "string"},
    {"sourceType": "real", "targetType": "double"},
    {"sourceType": "smalldatetime", "targetType": "datetime"},
    {"sourceType": "smallint", "targetType": "int"},
    {"sourceType": "smallmoney", "targetType": "decimal"},
    {"sourceType": "text", "targetType": "string"},
    {"sourceType": "time", "targetType": "datetime"},
    {"sourceType": "timestamp", "targetType": "string"},
    {"sourceType": "tinyint", "targetType": "int"},
    {"sourceType": "uniqueidentifier", "targetType": "string"},
    {"sourceType": "varbinary", "targetType": "string"},
    {"sourceType": "varchar", "targetType": "string"},
    {"sourceType": "xml", "targetType": "string"},
    {"sourceType": "sql_variant", "targetType": "string"},
]


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


class SqlServer(Plugin):
    def list_schemas(self) -> list[str]:
        return ["dbo"]

    def validate_connection(
        self, secret_resolver: SecretResolver, /, **properties: Any
    ) -> Exception | None:
        errors: list[dict[str, str]] = []
        if (props.get("auth.mode") or "").strip() not in {"sql_user"}:
            errors.append(
                {"key": "auth.mode", "message": "Unsupported auth.mode.", "level": "error"}
            )
            return errors
        for k in ("host", "database", "username", "password"):
            if not (props.get(k) or "").strip():
                errors.append({"key": k, "message": "Required field is missing.", "level": "error"})
        # bool fields are strings in extendedProperties
        for b in ("encrypt", "trustServerCertificate"):
            v = props.get(b)
            if v is None or v == "":
                continue
            _ = _truthy(v)
        return errors

    @staticmethod
    def get_ui_schema() -> dict[str, Any]:
        return {
            "title": "SQL Server connection",
            "authModes": [
                {
                    "id": "sql_user",
                    "label": "Username/Password",
                    "fields": [
                        {
                            "key": "auth.mode",
                            "label": "Authentication",
                            "type": "hidden",
                            "required": True,
                            "default": "sql_user",
                        },
                        {
                            "key": "host",
                            "label": "Host",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "key": "port",
                            "label": "Port",
                            "type": "number",
                            "required": False,
                            "default": "1433",
                        },
                        {
                            "key": "database",
                            "label": "Database",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "key": "username",
                            "label": "Username",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "key": "password",
                            "label": "Password",
                            "type": "secret",
                            "required": True,
                            "secret": True,
                        },
                        {
                            "key": "encrypt",
                            "label": "Encrypt",
                            "type": "boolean",
                            "required": False,
                            "default": "false",
                        },
                        {
                            "key": "trustServerCertificate",
                            "label": "Trust server certificate",
                            "type": "boolean",
                            "required": False,
                            "default": "true",
                        },
                    ],
                }
            ],
        }
