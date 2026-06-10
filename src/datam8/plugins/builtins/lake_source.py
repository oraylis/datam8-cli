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
from typing import Final

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


DATA_TYPE_MAPPINGS: Final[dict[str, str]] = {
    "Boolean": "bit",
    "Int8": "int",
    "Int16": "int",
    "Int32": "int",
    "Int64": "long",
    "UInt8": "int",
    "UInt16": "int",
    "UInt32": "long",
    "UInt64": "long",
    "Float32": "double",
    "Float64": "double",
    "Decimal": "decimal",
    "String": "string",
    "Utf8": "string",
    "Binary": "binary",
    "Date": "date",
    "Datetime": "datetime",
    "Time": "datetime",
    "Duration": "string",
    "List": "string",
    "Struct": "string",
}
"Mapping from source type to DataM8 internal type"


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

    def _build_abfss_url(self, container: str, path: str) -> str:
        account_name = self.extended_properties["storageAccountName"]
        return f"abfss://{container}@{account_name}.dfs.core.windows.net/{path}"

    def test_connection(self) -> Exception | None:
        try:
            file_systems = self._service_client.list_file_systems(timeout=10)
            next(iter(file_systems), None)
            self.logger.debug("Connection test successful")
            return None
        except Exception as err:
            self.logger.error(f"Connection test failed: {err}")
            return utils.create_error(err)

    def list_container(self) -> pl.DataFrame:
        """
        In ADLS Gen2, file systems are equivalent to schemas or databases.
        """
        try:
            file_systems = self._service_client.list_file_systems()
            schemas = [{"container": fs.name} for fs in file_systems]
            return pl.DataFrame(schemas)
        except Exception as err:
            raise utils.create_error(err)

    def list_blobs(self, container: str, path: str) -> pl.DataFrame:
        blobs = []
        try:
            fs_client = self._service_client.get_file_system_client(container)
            paths = fs_client.get_paths(path, recursive=False)

            for p in paths:
                blobs.append(
                    {
                        "container": container,
                        "name": p.name,
                        "type": "DIRECTORY" if p.is_directory else "BLOB",
                    }
                )
        except Exception as err:
            raise utils.create_error(err)

        return pl.DataFrame(blobs)

    def list_source(self, source_location: str | None = None, /) -> pl.DataFrame:
        if source_location is None or source_location == "":
            return self.list_container()

        container, path = self.parse_source_location(source_location)
        return self.list_blobs(container, path)

    def preview_data(self, source_location: str, *, limit: int = 10) -> pl.LazyFrame:
        """
        Supports Parquet, CSV, and JSON file formats using Polars native cloud storage.
        """
        container, path = self.parse_source_location(source_location)

        try:
            url = self._build_abfss_url(container, path)

            # Determine file type and read accordingly using Polars lazy API
            if path.endswith(".parquet"):
                lf = pl.scan_parquet(url, storage_options=self._storage_options)
            elif path.endswith(".csv"):
                lf = pl.scan_csv(url, storage_options=self._storage_options)
            elif path.endswith((".json", ".jsonl", ".ndjson")):
                lf = pl.scan_ndjson(url, storage_options=self._storage_options)
            else:
                lf = pl.scan_delta(url, storage_options=self._storage_options)

            return lf.head(limit)
        except Exception as err:
            raise utils.create_error(err)

    def get_table_metadata(self, source_location: str, /) -> TableMetadata:
        """
        Extracts column information from structured files (Parquet, CSV, JSON).
        For non-structured files, returns basic binary content metadata.
        Uses Polars lazy scanning to read only schema information efficiently.
        """
        container, path_ = self.parse_source_location(source_location)
        if container == "":
            raise utils.create_error(
                "A container (file system) needs to be provided for Azure Data Lake sources"
            )

        try:
            url = self._build_abfss_url(container, path_)

            # TODO: needs to be more dynamic like reading from a directory
            # does not necessarily be reading a single file

            # For structured files, try to get column information using lazy scanning
            if path_.endswith(".parquet"):
                lf = pl.scan_parquet(url, storage_options=self._storage_options)
            elif path_.endswith(".csv"):
                lf = pl.scan_csv(url, storage_options=self._storage_options)
            elif path_.endswith((".json", ".jsonl", ".ndjson")):
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

            return TableMetadata(metadata, SourceObject(schema_=container, name=path_, type="FILE"))

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
    def parse_source_location(source_location: str) -> tuple[str, str]:
        if "@" in source_location:
            container, path_ = source_location.rsplit("@", maxsplit=1)
            return container, path_
        return source_location, "/"

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
        global DATA_TYPE_MAPPINGS

        return [
            SourceDataTypeMapping(sourceType=src, targetType=trg)
            for src, trg in DATA_TYPE_MAPPINGS.items()
        ]

    @classmethod
    def resolve_source_type(cls, source_type: str, /) -> str:
        global DATA_TYPE_MAPPINGS

        if source_type not in DATA_TYPE_MAPPINGS:
            raise ValueError(f"'{source_type}' is not a configured type for '{cls.manifest().id}'")

        return DATA_TYPE_MAPPINGS[source_type]
