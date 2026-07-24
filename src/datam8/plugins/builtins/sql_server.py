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
from typing import Any, Final

import polars as pl
import typer

from datam8 import config, logging, utils
from datam8.plugins.base import Plugin, TableMetadata
from datam8_model.data_source import (
    AuthMode,
    ConnectionProperty,
    ConnectionPropertyValueType,
    DataSource,
    DataSourceType,
    SourceDataTypeMapping,
    SourceObject,
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
        Capability.PREVIEW_DATA,
        Capability.UI_SCHEMA,
        Capability.VALIDATION_CONNECTION,
    ],
)

DATA_TYPE_MAPPINGS: Final[dict[str, str]] = {
    "bit": "bit",
    # texts
    "uniqueidentifier": "string",
    "varbinary": "string",
    "varchar": "string",
    "xml": "string",
    "sql_variant": "string",
    "text": "text",
    "timestamp": "string",
    "nvarchar": "string",
    "nchar": "string",
    "ntext": "string",
    "image": "string",
    "char": "string",
    "binary": "string",
    # numbers
    "bigint": "long",
    "tinyint": "int",
    "real": "double",
    "smallint": "int",
    "smallmoney": "decimal",
    "numeric": "decimal",
    "int": "int",
    "money": "decimal",
    "decimal": "decimal",
    "float": "double",
    # dates / times
    "date": "date",
    "smalldatetime": "datetime",
    "datetime": "datetime",
    "datetime2": "datetime",
    "datetimeoffset": "datetime",
    "time": "datetime",
}
"Mapping from source type to DataM8 internal type"


class SqlServer(Plugin):
    """
    Plugin to interact with MS SQL Server. The connection is done using polars and connector-x which
    does not rely on any further packages or drivers at uses pyArrow internally.
    """

    __manifest: PluginManifest = manifest

    def __init__(
        self, manifest: PluginManifest, /, data_source: DataSource, data_source_type: DataSourceType
    ) -> None:
        super().__init__(manifest, data_source, data_source_type)
        SqlServer.validate_connection(data_source, data_source_type)

        self.logger.debug(f"Properties: {self.extended_properties}")

    def get_connection_string(self) -> str:
        mandatory: dict[str, Any] = {}
        optional: dict[str, Any] = {}

        for cp in self.get_connection_properties():
            match [cp.required, cp.default, cp.name]:
                case [True, _, _]:
                    mandatory[cp.name] = self.extended_properties[cp.name]
                case [False, None, str() as name] if name in self.extended_properties:
                    optional[name] = self.extended_properties[name]
                case [False, _ as default, str() as name] if name in self.extended_properties:
                    optional[name] = self.extended_properties.get(name, default)

        uri_template: str
        match mandatory:
            case {"authMode": "sql_user"}:
                assert "password" in optional
                assert "username" in optional

                mandatory["username"] = urllib.parse.quote_plus(optional.pop("username"))
                mandatory["password"] = urllib.parse.quote_plus(optional.pop("password"))

                uri_template = "mssql://{username}:{password}@{host}:{port}/{database}"

            case {"authMode": "windows"}:
                assert "trusted_connection" in optional

                uri_template = "mssql://@{host}:{port}/{database}"

            case {"authMode": _ as auth_mode}:
                raise utils.create_error(
                    ValueError(f"Unknown authMode {auth_mode} in {self._data_source.name}")
                )
            case _:
                raise utils.create_error(
                    ValueError(f"Missing authMode in {self._data_source.name}")
                )

        uri = uri_template.format(**mandatory)

        if len(optional) > 0:
            uri += "?" + "&".join([f"{k}={v}" for k, v in optional.items()])

        masked_uri = uri
        for cp in self.get_connection_properties():
            if (
                cp.name in {**mandatory, **optional}
                and cp.type == ConnectionPropertyValueType.SECRET
            ):
                to_replace: Any = mandatory.get(cp.name, optional.get(cp.name))
                masked_uri = masked_uri.replace(str(to_replace), "*****")

        self.logger.debug(f"Created connection string: {masked_uri}")

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

    def list_source(self, source_location: str | None = None, /) -> pl.DataFrame:
        if source_location == "" or source_location is None:
            return self.list_schemas()

        schema, _ = self.parse_source_location(source_location)
        return self.list_tables(schema)

    def list_schemas(self) -> pl.DataFrame:
        database = (self._data_source.extendedProperties or {})["database"]
        query = f"""
            select
                schema_name as [schema]
            from
                [information_schema].[schemata]
            where 1=1
                and catalog_name = '{database}'
        """

        result = self._execute_query(query)
        return result

    def list_tables(self, schema: str | None = None) -> pl.DataFrame:
        database = (self._data_source.extendedProperties or {})["database"]

        query = f"""
            select
                table_schema as [schema],
                table_name as [name],
                table_type as [type]
            from [information_schema].[tables]
            where 1=1
                and table_catalog = '{database}'
        """
        if schema is not None:
            query += f" and table_schema = '{schema}'"

        return self._execute_query(query)

    def preview_data(self, source_location: str, *, limit: int = 10) -> pl.LazyFrame:
        schema, table = self.parse_source_location(source_location)

        query = f"select top {limit} * from [{schema}].[{table}]"
        return self._execute_query(query).lazy()

    def get_table_metadata(self, source_location: str) -> TableMetadata:
        schema, table = self.parse_source_location(source_location)

        query = f"""
            select
                c.ordinal_position as [ordinal]
            ,   c.column_name as [name]
            ,   c.data_type as [dataType]
            ,   c.numeric_precision as [numericPrecision]
            ,   c.numeric_scale as [numericScale]
            ,   coalesce(c.character_maximum_length, c.datetime_precision) as [maxLength]
            ,   c.is_nullable as [isNullable]
            ,   case when pk.column_name is not null then 1 else 0 end as [isPrimaryKey]
            from [information_schema].[tables] as t
                join [information_schema].[columns] as c
                    on c.table_name = t.table_name
                    and c.table_schema = t.table_schema
                    and c.table_catalog = t.table_catalog
                left join (
                    select
                        kcu.table_schema
                    ,   kcu.table_name
                    ,   kcu.column_name
                    from [information_schema].[table_constraints] as tc
                        join [information_schema].[key_column_usage] as kcu
                            on kcu.constraint_name = tc.constraint_name
                            and kcu.table_schema = tc.table_schema
                            and kcu.table_catalog = tc.table_catalog
                    where tc.constraint_type = 'PRIMARY KEY'
                ) as pk
                    on pk.table_schema = c.table_schema
                    and pk.table_name = c.table_name
                    and pk.column_name = c.column_name
            where 1=1
                and t.table_name = '{table}'
                and t.table_schema = '{schema}'
            order by
                ordinal_position
        """

        raw_rows = self._execute_query(query).to_dicts()
        if not raw_rows:
            raise utils.create_error(
                f"Table [{schema}].[{table}] does not exist in '{self._data_source.name}'"
            )

        def first_non_null(row: dict[str, Any], *keys: str) -> Any:
            return next((row[key] for key in keys if row.get(key) is not None), None)

        def nullable_int(value: Any, *, allow_zero: bool = False) -> int | None:
            if value is None or str(value).strip() == "":
                return None
            number = int(value)
            minimum = 0 if allow_zero else 1
            return number if number >= minimum else None

        def boolean(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in {"1", "true", "yes", "y"}

        rows: list[dict[str, Any]] = []
        for row in raw_rows:
            name = first_non_null(row, "name", "COLUMN_NAME", "column_name")
            ordinal = first_non_null(row, "ordinal", "ORDINAL_POSITION", "ordinal_position")
            data_type = first_non_null(row, "dataType", "DATA_TYPE", "data_type")
            is_nullable = first_non_null(row, "isNullable", "IS_NULLABLE", "is_nullable")
            ordinal_number = nullable_int(ordinal)

            if (
                name is None
                or data_type is None
                or is_nullable is None
                or ordinal_number is None
            ):
                raise utils.create_error(
                    ValueError(
                        f"Invalid source metadata row for [{schema}].[{table}] "
                        f"in '{self._data_source.name}': {row}"
                    )
                )

            rows.append(
                {
                    "name": str(name),
                    "ordinal": ordinal_number,
                    "dataType": str(data_type),
                    "maxLength": nullable_int(
                        first_non_null(
                            row,
                            "maxLength",
                            "CHARACTER_MAXIMUM_LENGTH",
                            "character_maximum_length",
                        )
                    ),
                    "numericPrecision": nullable_int(
                        first_non_null(
                            row,
                            "numericPrecision",
                            "NUMERIC_PRECISION",
                            "numeric_precision",
                        )
                    ),
                    "numericScale": nullable_int(
                        first_non_null(
                            row,
                            "numericScale",
                            "NUMERIC_SCALE",
                            "numeric_scale",
                        ),
                        allow_zero=True,
                    ),
                    "isNullable": boolean(is_nullable),
                    "isPrimaryKey": boolean(
                        first_non_null(
                            row,
                            "isPrimaryKey",
                            "IS_PRIMARY_KEY",
                            "is_primary_key",
                        )
                        or False
                    ),
                }
            )

        return TableMetadata(
            pl.DataFrame(rows),
            SourceObject.from_dict(
                {"schema": schema, "name": table, "type": "TABLE/VIEW"}
            ),
        )

    @classmethod
    def validate_connection(
        cls, data_source: DataSource, /, data_source_type: DataSourceType
    ) -> Exception | None:
        # TODO: implement additional plugin specific validation logics
        return None

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls.__manifest

    @staticmethod
    def parse_source_location(source_location: str) -> tuple[str, str]:
        if "." in source_location:
            schema, table = source_location.split(".", maxsplit=1)
            return schema.strip("[").strip("]"), table.strip("]").strip("[")
        return source_location.strip("[").strip("]"), ""

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_auth_modes() -> list[AuthMode]:
        auth_modes = [
            AuthMode(
                name="sql_user",
                displayName="Username / Password",
                required=["username", "password"],
                optional=["trust_server_certificate", "trust_server_certificate_ca", "encrypt"],
            ),
            AuthMode(
                name="windows",
                displayName="Windows Authentication",
                required=["trusted_connection"],
                optional=["trust_server_certificate", "trust_server_certificate_ca", "encrypt"],
            ),
        ]

        return auth_modes

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_connection_properties() -> list[ConnectionProperty]:
        cp = [
            ConnectionProperty(
                name="authMode", type=ConnectionPropertyValueType.STRING, required=True
            ),
            ConnectionProperty(name="host", type=ConnectionPropertyValueType.STRING, required=True),
            ConnectionProperty(
                name="database", type=ConnectionPropertyValueType.STRING, required=True
            ),
            ConnectionProperty(
                name="port", type=ConnectionPropertyValueType.NUMBER, required=True, default=1433
            ),
            ConnectionProperty(
                name="username", type=ConnectionPropertyValueType.STRING, required=False
            ),
            ConnectionProperty(
                name="password", type=ConnectionPropertyValueType.SECRET, required=False
            ),
            ConnectionProperty(
                name="trust_server_certificate",
                required=False,
                default=False,
                type=ConnectionPropertyValueType.BOOLEAN,
                description="Trust unverifyable certificates, e.g. self-signed",
            ),
            ConnectionProperty(
                name="trust_server_certificate_ca",
                required=False,
                type=ConnectionPropertyValueType.BOOLEAN,
                description="Path to a root ca to verify the server certificate against",
            ),
            ConnectionProperty(
                name="encrypt",
                required=False,
                default=True,
                type=ConnectionPropertyValueType.BOOLEAN,
                description="Activate SSL encryption",
            ),
            ConnectionProperty(
                name="trusted_connection",
                required=False,
                default=False,
                type=ConnectionPropertyValueType.BOOLEAN,
                description="Enables Windows Authentication",
            ),
        ]
        return cp

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        global DATA_TYPE_MAPPINGS

        data_types = [
            SourceDataTypeMapping(sourceType=src, targetType=trg)
            for src, trg in DATA_TYPE_MAPPINGS.items()
        ]
        return data_types

    @classmethod
    def resolve_source_type(cls, source_type: str, /) -> str:
        global DATA_TYPE_MAPPINGS

        if source_type not in DATA_TYPE_MAPPINGS:
            raise ValueError(f"'{source_type}' is not a configured type for '{cls.manifest().id}'")

        return DATA_TYPE_MAPPINGS[source_type]
