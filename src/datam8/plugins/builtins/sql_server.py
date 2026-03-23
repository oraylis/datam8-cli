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

import functools
import urllib.parse
from typing import Any

import polars as pl
import typer

from datam8 import config, logging, utils
from datam8.plugins.base import Plugin
from datam8.secrets import SecretResolver
from datam8_model.data_source import (
    ConnectionProperty,
    DataSource,
    DataSourceType,
    SourceDataTypeMapping,
)
from datam8_model.plugin import Capability, PluginManifest

try:
    import connectorx as _  # noqa: F401
except ModuleNotFoundError as err:
    typer.echo("Required modules for SQL Server Plugin not installed - Install the 'sql' extra")
    raise typer.Exit(1) from err


logger = logging.getLogger(__name__)

manifest = PluginManifest(
    id="builtin:SQLServer",
    displayName="SQL Server (built-in)",
    version=config.get_version(),
    entryPoint="datam8.plugins.builtins.sql_server:SqlServer",
    capabilities=[
        Capability.METADATA,
        Capability.UI_SCHEMA,
        Capability.VALIDATION_CONNECTION,
    ],
)


class SqlServer(Plugin):
    """
    Plugin to interact with MS SQL Server. The connection is done using polars and connector-x which
    does not rely on any further packages or drivers at uses pyArrow internally.
    """

    manifest: PluginManifest = manifest

    def __init__(
        self, manifest: PluginManifest, /, data_source: DataSource, data_source_type: DataSourceType
    ) -> None:
        super().__init__(manifest, data_source, data_source_type)
        SqlServer.validate_connection(data_source, data_source_type)

        self.logger.debug(f"Properties: {self.connection_properties}")

    def get_connection_string(self) -> str:
        # mandatory options
        username = self.connection_properties.pop("username")
        host = self.connection_properties.pop("host")
        database = self.connection_properties.pop("database")
        port = self.connection_properties.pop("port")

        password_ref = self.connection_properties.pop(
            "password_ref", f"sources/SQLServer/{self._data_source.name}"
        )

        password = SecretResolver().get_secret(password_ref)
        if password is None:
            raise utils.create_error(KeyError(f"Missing ref from secret store: {password_ref}"))

        password = urllib.parse.quote_plus(password)
        uri = f"mssql://{username}:{password}@{host}:{port}/{database}"

        if len(self.connection_properties) > 0:
            uri += "?" + "&".join([f"{k}={v}" for k, v in self.connection_properties.items()])

        sanitized_uri = uri.replace(password, "*****")
        self.logger.debug(f"Created connection string: {sanitized_uri}")

        return uri

    def _execute_query(self, query: str, /, pre_execution_query: list[str] = []) -> pl.DataFrame:
        uri = self.get_connection_string()
        try:
            self.logger.debug(f"Executing: {query}")
            result = pl.read_database_uri(query, uri, pre_execution_query=pre_execution_query)
            self.logger.debug(f"Result: {result}")
            return result
        except Exception as err:
            raise utils.create_error(err)

    def test_connection(self) -> Exception | None:
        result = self._execute_query("select 'connected' as [status]")
        if isinstance(result, Exception):
            return result
        return None

    def list_schemas(self) -> pl.DataFrame:
        database = (self._data_source.extendedProperties or {})["database"]
        query = f"""
            select
                catalog_name, schema_name, schema_owner
            from
                [information_schema].[schemata]
            where 1=1
                and catalog_name = '{database}'
        """

        result = self._execute_query(query)
        return result

    def list_tables(self, schema: str | None = None) -> pl.DataFrame:
        database = (self._data_source.extendedProperties or {})["database"]
        if schema is None:
            raise utils.create_error("A schema needs to be provided for SQL Server sources")

        query = f"""
            select *
            from [information_schema].[tables]
            where 1=1
                and table_catalog = '{database}'
                and table_schema = '{schema}'
        """

        return self._execute_query(query)

    def preview_data(self, table: str, schema: str | None = None, limit: int = 10) -> pl.LazyFrame:
        if schema is None:
            raise utils.create_error("A schema needs to be provided for SQL Server sources")

        query = f"select top {limit} * from [{schema}].[{table}]"
        return self._execute_query(query).lazy()

    def get_table_metadata(self, table: str, schema: str | None = None) -> pl.DataFrame:
        if schema is None:
            raise utils.create_error("A schema needs to be provided for SQL Server sources")

        query = f"""
            select c.*
            from [information_schema].[tables] as t
                join [information_schema].[columns] as c
                    on c.table_name = t.table_name
                    and c.table_schema = t.table_schema
                    and c.table_catalog = t.table_catalog
            where 1=1
                and t.table_name = '{table}'
                and t.table_schema = '{schema}'
            order by
                ordinal_position
        """

        result = self._execute_query(query).drop("TABLE_CATALOG", "TABLE_SCHEMA", "TABLE_NAME")
        if result.is_empty():
            raise utils.create_error(
                f"Table [{schema}].[{table}] does not exist in '{self._data_source.name}'"
            )

        return result

    @classmethod
    def validate_connection(
        cls, data_source: DataSource, /, data_source_type: DataSourceType
    ) -> Exception | None:
        # TODO: implement additional plugin specific validation logics
        return None

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_ui_schema() -> dict[str, Any]:
        schema_ = {
            "titel": "SQL Server Connection",
            "authModes": [],
            "fields": [],
        }
        schema_["authModes"].append(
            {
                "id": "sql_user",
                "label": "Username/Password",
                "fields": [],
            }
        )
        schema_["authModes"].append(
            {
                "id": "entry_mfa",
                "label": "EntraID with MFA",
                "fields": [],
            }
        )

        return schema_

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_connection_properties() -> list[ConnectionProperty]:
        cp = [
            ConnectionProperty(name="authMode", required=True),
            ConnectionProperty(name="username", required=True),
            ConnectionProperty(name="host", required=True),
            ConnectionProperty(name="database", required=True),
            ConnectionProperty(name="port", required=True, default=1433),
            ConnectionProperty(
                name="trust_server_certificate",
                required=False,
                default=False,
                description="Trust unverifyable certificates, e.g. self-signed",
            ),
            ConnectionProperty(
                name="trust_server_certificate_ca",
                required=False,
                description="Path to a root ca to verify the server certificate against",
            ),
            ConnectionProperty(
                name="encrypt",
                required=False,
                default=True,
                description="Activate SSL encryption",
            ),
            ConnectionProperty(
                name="trusted_connection",
                required=False,
                default=False,
                description="Enables Windows Authentication",
            ),
        ]
        return cp

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        data_types = [
            SourceDataTypeMapping(sourceType="bit", targetType="boolean"),
            # texts
            SourceDataTypeMapping(sourceType="uniqueidentifier", targetType="string"),
            SourceDataTypeMapping(sourceType="varbinary", targetType="string"),
            SourceDataTypeMapping(sourceType="varchar", targetType="string"),
            SourceDataTypeMapping(sourceType="xml", targetType="string"),
            SourceDataTypeMapping(sourceType="sql_variant", targetType="string"),
            SourceDataTypeMapping(sourceType="text", targetType="text"),
            SourceDataTypeMapping(sourceType="timestamp", targetType="string"),
            SourceDataTypeMapping(sourceType="nvarchar", targetType="string"),
            SourceDataTypeMapping(sourceType="nchar", targetType="string"),
            SourceDataTypeMapping(sourceType="ntext", targetType="string"),
            SourceDataTypeMapping(sourceType="image", targetType="string"),
            SourceDataTypeMapping(sourceType="char", targetType="string"),
            SourceDataTypeMapping(sourceType="binary", targetType="string"),
            # numbers
            SourceDataTypeMapping(sourceType="bigint", targetType="long"),
            SourceDataTypeMapping(sourceType="tinyint", targetType="int"),
            SourceDataTypeMapping(sourceType="real", targetType="double"),
            SourceDataTypeMapping(sourceType="smallint", targetType="int"),
            SourceDataTypeMapping(sourceType="smallmoney", targetType="decimal"),
            SourceDataTypeMapping(sourceType="numeric", targetType="decimal"),
            SourceDataTypeMapping(sourceType="int", targetType="int"),
            SourceDataTypeMapping(sourceType="money", targetType="decimal"),
            SourceDataTypeMapping(sourceType="decimal", targetType="decimal"),
            SourceDataTypeMapping(sourceType="float", targetType="double"),
            # dates / times
            SourceDataTypeMapping(sourceType="date", targetType="datetime"),
            SourceDataTypeMapping(sourceType="smalldatetime", targetType="datetime"),
            SourceDataTypeMapping(sourceType="datetime", targetType="datetime"),
            SourceDataTypeMapping(sourceType="datetime2", targetType="datetime"),
            SourceDataTypeMapping(sourceType="datetimeoffset", targetType="datetime"),
            SourceDataTypeMapping(sourceType="time", targetType="datetime"),
        ]
        return data_types
