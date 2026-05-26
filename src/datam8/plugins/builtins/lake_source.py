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
import enum
import functools

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
)
from datam8_model.plugin import Capability, PluginManifest

try:
    from azure.identity import (
        AzureCliCredential,
        ChainedTokenCredential,
        ClientSecretCredential,
        DefaultAzureCredential,
        InteractiveBrowserCredential,
    )
    from azure.storage.filedatalake import DataLakeServiceClient
except ModuleNotFoundError as err:
    typer.echo(
        "Required modules for Azure Data Lake Plugin not installed - Install the 'azure' extra"
    )
    raise typer.Exit(1) from err


logger = logging.getLogger(__name__)


class AzureAuthMode(enum.StrEnum):
    """Authentication modes for Azure Data Lake Storage Gen2."""

    DEFAULT = "default"
    SERVICE_PRINCIPAL = "service_principal"
    MANAGED_IDENTITY = "managed_identity"


manifest_azure = PluginManifest(
    id="builtin:AzureDataLake",
    displayName="Azure Data Lake Gen2 (built-in)",
    version=config.get_version(),
    entryPoint="datam8.plugins.builtins.lake_source:AzureDataLake",
    capabilities=[
        Capability.METADATA,
        Capability.UI_SCHEMA,
        Capability.VALIDATION_CONNECTION,
    ],
)


class AzureDataLake(Plugin):
    """
    Plugin to interact with Azure Data Lake Storage Gen2.

    This plugin provides connectivity to Azure Data Lake Storage Gen2 using Polars
    built-in cloud storage integration. It supports multiple authentication modes
    including Service Principal, Managed Identity, and default credentials (Azure CLI/Browser).

    Attributes
    ----------
    _service_client : DataLakeServiceClient
        Azure Data Lake service client for connection validation and metadata operations.
    _storage_options : dict[str, str]
        Storage options for Polars cloud storage integration.

    Notes
    -----
    The plugin uses Polars native cloud storage capabilities with scan_parquet, scan_csv,
    and scan_ndjson for efficient data reading without downloading files locally.
    """

    __manifest: PluginManifest = manifest_azure

    def __init__(
        self, manifest: PluginManifest, /, data_source: DataSource, data_source_type: DataSourceType
    ) -> None:
        super().__init__(manifest, data_source, data_source_type)
        AzureDataLake.validate_connection(data_source, data_source_type)

        self.logger.debug(f"Properties: {self.extended_properties}")

        # Create credential and service client
        self._credential = self._get_credential()
        self._service_client = self._get_service_client()
        self._storage_options = self._get_storage_options()

    def _get_credential(self) -> ClientSecretCredential | ChainedTokenCredential:
        auth_mode_str = self.extended_properties.get("authMode", AzureAuthMode.DEFAULT.value)

        if auth_mode_str not in AzureAuthMode._value2member_map_:
            raise utils.create_error(
                ValueError(
                    f"Unknown authMode '{auth_mode_str}' in {self._data_source.name}. "
                    f"Valid options: {', '.join([mode.value for mode in AzureAuthMode])}"
                )
            )

        match AzureAuthMode(auth_mode_str):
            case AzureAuthMode.SERVICE_PRINCIPAL:
                tenant_id = self.extended_properties["tenantId"]
                client_id = self.extended_properties["clientId"]
                client_secret = self.extended_properties["clientSecret"]

                credential = ClientSecretCredential(
                    tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
                )
                self.logger.debug("Using Service Principal authentication")

            case AzureAuthMode.MANAGED_IDENTITY:
                credential = DefaultAzureCredential()
                self.logger.debug("Using Managed Identity authentication")

            case AzureAuthMode.DEFAULT:
                credential = ChainedTokenCredential(
                    AzureCliCredential(), InteractiveBrowserCredential()
                )
                self.logger.debug("Using default authentication (Azure CLI -> Interactive Browser)")

        return credential

    def _get_service_client(self) -> DataLakeServiceClient:
        account_name = self.extended_properties["storageAccountName"]
        account_url = f"https://{account_name}.dfs.core.windows.net"
        return DataLakeServiceClient(account_url=account_url, credential=self._credential)

    def _get_storage_options(self) -> dict[str, str]:
        storage_options: dict[str, str] = {
            "account_name": self.extended_properties["storageAccountName"],
            "bearer_token": self._credential.get_token("https://storage.azure.com/.default").token,
        }

        return storage_options

    def _build_abfss_url(self, schema: str, table: str) -> str:
        account_name = self.extended_properties["storageAccountName"]
        file_system, path = schema.split("/", 1) if "/" in schema else (schema, "")
        return f"abfss://{file_system}@{account_name}.dfs.core.windows.net/{path}/{table}"

    def test_connection(self) -> Exception | None:
        try:
            file_systems = self._service_client.list_file_systems(timeout=10)
            next(iter(file_systems), None)
            self.logger.debug("Connection test successful")
            return None
        except Exception as err:
            self.logger.error(f"Connection test failed: {err}")
            return utils.create_error(err)

    def list_schemas(self) -> pl.DataFrame:
        """
        In ADLS Gen2, file systems are equivalent to schemas or databases.
        """
        try:
            file_systems = self._service_client.list_file_systems()
            schemas = [{"schema": fs.name} for fs in file_systems]
            return pl.DataFrame(schemas)
        except Exception as err:
            raise utils.create_error(err)

    def list_tables(self, schema: str | None = None) -> pl.DataFrame:
        tables = []

        try:
            if schema is not None:
                file_system, rel_path = schema.split("/", 1) if "/" in schema else (schema, "")
                file_system_client = self._service_client.get_file_system_client(file_system)
                paths = file_system_client.get_paths(rel_path, recursive=False)

                for path in paths:
                    tables.append(
                        {
                            "schema": schema,
                            "name": path.name.replace(f"{rel_path}/", ""),
                            "type": "DIRECTORY" if path.is_directory else "FILE",
                        }
                    )
            else:
                file_systems = self._service_client.list_file_systems()
                for fs in file_systems:
                    file_system_client = self._service_client.get_file_system_client(fs)
                    paths = file_system_client.get_paths(recursive=False)

                    for rel_path in paths:
                        tables.append(
                            {
                                "schema": fs.name,
                                "name": rel_path.name,
                                "type": "DIRECTORY" if rel_path.is_directory else "FILE",
                            }
                        )
        except Exception as err:
            raise utils.create_error(err)

        return pl.DataFrame(tables)

    def preview_data(
        self, table: str, /, schema: str | None = None, *, limit: int = 10
    ) -> pl.LazyFrame:
        """
        Supports Parquet, CSV, and JSON file formats using Polars native cloud storage.
        """
        if schema is None:
            raise utils.create_error(
                "A schema (file system / container) needs to be provided for Azure Data Lake sources"
            )

        try:
            url = self._build_abfss_url(schema, table)

            # Determine file type and read accordingly using Polars lazy API
            if table.endswith(".parquet"):
                lf = pl.scan_parquet(url, storage_options=self._storage_options)
            elif table.endswith(".csv"):
                lf = pl.scan_csv(url, storage_options=self._storage_options)
            elif table.endswith((".json", ".jsonl", ".ndjson")):
                lf = pl.scan_ndjson(url, storage_options=self._storage_options)
            else:
                lf = pl.scan_delta(url, storage_options=self._storage_options)

            return lf.head(limit)
        except Exception as err:
            raise utils.create_error(err)

    def get_table_metadata(self, table: str, schema: str | None = None) -> TableMetadata:
        """
        Extracts column information from structured files (Parquet, CSV, JSON).
        For non-structured files, returns basic binary content metadata.
        Uses Polars lazy scanning to read only schema information efficiently.
        """
        if schema is None:
            raise utils.create_error(
                "A schema (file system) needs to be provided for Azure Data Lake sources"
            )

        try:
            url = self._build_abfss_url(schema, table)

            # TODO: needs to be more dynamic like reading from a directory
            # does not necessarily be reading a single file

            # For structured files, try to get column information using lazy scanning
            if table.endswith(".parquet"):
                lf = pl.scan_parquet(url, storage_options=self._storage_options)
            elif table.endswith(".csv"):
                lf = pl.scan_csv(url, storage_options=self._storage_options)
            elif table.endswith((".json", ".jsonl", ".ndjson")):
                lf = pl.scan_ndjson(url, storage_options=self._storage_options)
            else:
                # if something else is provided assume delta table/directory
                lf = pl.scan_delta(url, storage_options=self._storage_options)

            polars_schema = lf.collect_schema()
            metadata = pl.DataFrame(
                {
                    "ordinal": list(range(1, len(polars_schema) + 1)),
                    "name": list(polars_schema.names()),
                    "dataType": [str(dtype.base_type()) for dtype in polars_schema.values()],
                    "numericPrecision": [
                        dtype.precision if isinstance(dtype, pl.Decimal) else None
                        for dtype in polars_schema.values()
                    ],
                    "numericScale": [
                        dtype.scale if isinstance(dtype, pl.Decimal) else None
                        for dtype in polars_schema.values()
                    ],
                    "maxLength": [None for _ in range(len(polars_schema))],
                },
                schema_overrides={
                    "numericPrecision": pl.Int64,
                    "numericScale": pl.Int64,
                    "maxLength": pl.Int64,
                },
            )

            return TableMetadata(metadata)

        except Exception as err:
            raise utils.create_error(err)

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
    def create_source_location(table: str, schema: str | None = None) -> str:
        return f"{schema}/{table}" if schema else table

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_auth_modes() -> list[AuthMode]:
        auth_modes = [
            AuthMode(
                name=AzureAuthMode.DEFAULT.value,
                displayName="Default (Azure CLI / Interactive Browser)",
                required=[],
                optional=[],
            ),
            AuthMode(
                name=AzureAuthMode.SERVICE_PRINCIPAL.value,
                displayName="Service Principal",
                required=["tenantId", "clientId", "clientSecret"],
                optional=[],
            ),
            AuthMode(
                name=AzureAuthMode.MANAGED_IDENTITY.value,
                displayName="Managed Identity",
                required=[],
                optional=[],
            ),
        ]
        return auth_modes

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_connection_properties() -> list[ConnectionProperty]:
        cp = [
            ConnectionProperty(
                name="authMode",
                type=ConnectionPropertyValueType.STRING,
                required=False,
                default=AzureAuthMode.DEFAULT.value,
                description=f"Authentication mode: {', '.join([mode.value for mode in AzureAuthMode])}",
            ),
            ConnectionProperty(
                name="storageAccountName",
                type=ConnectionPropertyValueType.STRING,
                required=True,
                description="Azure Storage Account name",
            ),
            ConnectionProperty(
                name="tenantId",
                type=ConnectionPropertyValueType.STRING,
                required=False,
                description="Azure AD Tenant ID (for Service Principal auth)",
            ),
            ConnectionProperty(
                name="clientId",
                type=ConnectionPropertyValueType.STRING,
                required=False,
                description="Application (Client) ID (for Service Principal auth)",
            ),
            ConnectionProperty(
                name="clientSecret",
                type=ConnectionPropertyValueType.SECRET,
                required=False,
                description="Client Secret (for Service Principal auth)",
            ),
        ]
        return cp

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        """
        Maps Polars data types (read from Parquet, CSV, JSON files) to target types.
        """
        data_types = [
            # Polars data types to target types
            SourceDataTypeMapping(sourceType="Boolean", targetType="boolean"),
            SourceDataTypeMapping(sourceType="Int8", targetType="int"),
            SourceDataTypeMapping(sourceType="Int16", targetType="int"),
            SourceDataTypeMapping(sourceType="Int32", targetType="int"),
            SourceDataTypeMapping(sourceType="Int64", targetType="long"),
            SourceDataTypeMapping(sourceType="UInt8", targetType="int"),
            SourceDataTypeMapping(sourceType="UInt16", targetType="int"),
            SourceDataTypeMapping(sourceType="UInt32", targetType="long"),
            SourceDataTypeMapping(sourceType="UInt64", targetType="long"),
            SourceDataTypeMapping(sourceType="Float32", targetType="double"),
            SourceDataTypeMapping(sourceType="Float64", targetType="double"),
            SourceDataTypeMapping(sourceType="Decimal", targetType="decimal"),
            SourceDataTypeMapping(sourceType="String", targetType="string"),
            SourceDataTypeMapping(sourceType="Utf8", targetType="string"),
            SourceDataTypeMapping(sourceType="Binary", targetType="binary"),
            SourceDataTypeMapping(sourceType="Date", targetType="datetime"),
            SourceDataTypeMapping(sourceType="Datetime", targetType="datetime"),
            SourceDataTypeMapping(sourceType="Time", targetType="datetime"),
            SourceDataTypeMapping(sourceType="Duration", targetType="string"),
            SourceDataTypeMapping(sourceType="List", targetType="string"),
            SourceDataTypeMapping(sourceType="Struct", targetType="string"),
        ]
        return data_types
