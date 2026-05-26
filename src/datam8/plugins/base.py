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

import abc
import functools
from collections.abc import Iterator
from typing import Any

import polars as pl

from datam8 import logging, utils
from datam8.secrets import SecretResolver
from datam8_model.data_source import (
    AuthMode,
    ConnectionProperty,
    ConnectionPropertyValueType,
    DataSource,
    DataSourceType,
    SourceDataTypeMapping,
    SourceField,
    SourceObject,
)
from datam8_model.plugin import Capability, PluginManifest, UiAuthMode, UiField, UiSchema

VALIDATION_CONNECTION = Capability.VALIDATION_CONNECTION
METADATA = Capability.METADATA
UI_SCHEMA = Capability.UI_SCHEMA

logger = logging.getLogger(__name__)


class TableMetadata:
    """
    Wrapper for table metadata stored as a Polars DataFrame.

    Provides conversion methods to transform metadata DataFrame into SourceField objects.
    Validates the DataFrame structure on initialization.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame containing table metadata with columns:
        - name : str
            Name of the column
        - dataType : str
            Data type of the column
        - ordinal : int
            1-indexed position of the column
        Optional columns:
        - isNullable : bool
            Whether the column is nullable (defaults to True)
        - maxLength : int
            Maximum length for character types
        - numericPrecision : int
            Precision for numeric types
        - numericScale : int
            Scale for numeric types
        - isPrimaryKey : bool
            Whether the column is a primary key
    source_object : SourceObject
        The source object (table/view/file) that this metadata describes.

    Raises
    ------
    ValueError
        If required columns (name, dataType, ordinal) are missing from the DataFrame.
    """

    def __init__(self, df: pl.DataFrame, /, source_object: SourceObject | None = None):
        self._df = df
        self.source_object = source_object
        self.__validate_df()

    @property
    def dataframe(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

    def __validate_df(self) -> None:
        required_columns = {"name", "dataType", "ordinal"}
        df_columns = set(self._df.columns)

        if not required_columns.issubset(df_columns):
            missing = required_columns - df_columns
            raise utils.create_error(
                ValueError(f"Missing required columns in metadata DataFrame: {missing}")
            )

        # Add missing optional columns with appropriate defaults
        optional_columns: dict[str, pl.Expr] = {}

        if "isNullable" not in df_columns:
            optional_columns["isNullable"] = pl.lit(True)
        else:
            optional_columns["isNullable"] = pl.col("isNullable").fill_null(True)

        if "maxLength" not in df_columns:
            optional_columns["maxLength"] = pl.lit(None)

        if "numericPrecision" not in df_columns:
            optional_columns["numericPrecision"] = pl.lit(None)

        if "numericScale" not in df_columns:
            optional_columns["numericScale"] = pl.lit(None)

        if "isPrimaryKey" not in df_columns:
            optional_columns["isPrimaryKey"] = pl.lit(False)
        else:
            optional_columns["isPrimaryKey"] = pl.col("isPrimaryKey").fill_null(False)

        self._df = self._df.with_columns(**optional_columns)

    def iter_source_fields(self) -> Iterator[SourceField]:
        """
        Iterate over SourceField objects from the metadata DataFrame.

        Yields
        ------
        SourceField
            SourceField objects representing table columns, yielded one at a time
            in ordinal position order.
        """
        for row in self._df.iter_rows(named=True):
            yield SourceField(
                name=row["name"],
                ordinal=row["ordinal"],
                dataType=row["dataType"],
                maxLength=row.get("maxLength"),
                numericPrecision=row.get("numericPrecision"),
                numbericScale=row.get("numericScale"),
                isNullable=row["isNullable"],
                isPrimaryKey=row["isPrimaryKey"],
            )


class MissingCapabilityError(Exception):
    """
    Exception raised when a plugin method requires a capability not supported by the plugin.

    Parameters
    ----------
    capability : Capability
        The required capability that is missing.
    data_source : DataSource | None, optional
        The data source for which the capability is missing.
    """

    def __init__(self, capability: Capability, data_source: DataSource | None = None):
        self.capability = capability
        self.data_source = data_source
        self.msg = f"Plugin is missing {capability}"

        if self.data_source is not None:
            self.msg += f" in {self.data_source}"

        super().__init__(self.msg)


class Plugin(abc.ABC):
    """
    Abstract base class for all DataM8 data source plugins.

    Plugins provide data source connectivity, metadata extraction, and data preview
    capabilities. Each plugin must implement abstract methods and define its
    capabilities through a manifest.

    Parameters
    ----------
    manifest : PluginManifest
        The plugin manifest containing metadata and capabilities.
    data_source : DataSource
        The data source configuration to connect to.
    data_source_type : DataSourceType
        The data source type definition with connection properties.

    Raises
    ------
    Exception
        If connection validation fails during initialization.
    """

    def __init__(
        self, manifest: PluginManifest, /, data_source: DataSource, data_source_type: DataSourceType
    ) -> None:
        self._manifest: PluginManifest = manifest
        self._data_source: DataSource = data_source
        self._data_source_type: DataSourceType = data_source_type
        self.logger = logging.getLogger(f"datam8.plugins.{data_source.type}.{data_source.name}")

        error = Plugin.validate_connection(data_source, data_source_type)
        if error is not None:
            raise utils.create_error(error)

    def __repr__(self) -> str:
        return f"Plugin(id='{self._manifest.id}' data_source='{self._data_source.name}')"

    @functools.cached_property
    def extended_properties(self) -> dict[str, Any]:
        """
        Get extended connection properties with defaults and resolved secrets.

        Merges data source extended properties with defaults from the data source type.
        Resolves any SECRET type properties using the SecretResolver.

        Returns
        -------
        dict[str, Any]
            Dictionary of connection properties with resolved values.

        Raises
        ------
        MissingCapabilityError
            If the plugin does not support connection validation.
        ValueError
            If a secret reference is not a string or cannot be resolved.
        """
        if not self.is_capable_of(VALIDATION_CONNECTION):
            raise utils.create_error(MissingCapabilityError(VALIDATION_CONNECTION))

        assert self._data_source.extendedProperties is not None
        base = dict(self._data_source.extendedProperties)

        for cp in self._data_source_type.connectionProperties:
            if cp.name not in base and cp.default is not None:
                base[cp.name] = cp.default
            if cp.type == ConnectionPropertyValueType.SECRET and cp.name in base:
                secret_ref = base.pop(cp.name)
                if not isinstance(secret_ref, str):
                    raise utils.create_error(ValueError("A secret ref needs to be of type string"))

                secret = SecretResolver().get_secret(secret_ref)
                if secret is None:
                    raise utils.create_error(
                        ValueError(f"Could not resolve secret ref: {secret_ref}")
                    )
                base[cp.name] = secret

        return base

    def get_manifest(self) -> PluginManifest:
        """
        Get the plugin manifest.

        Returns
        -------
        PluginManifest
            The plugin manifest containing metadata and capabilities.
        """
        return self._manifest

    def test_connection(self) -> Exception | None:
        """
        Test the connection to the data source.

        Returns
        -------
        Exception | None
            None if connection is successful, Exception object if connection fails.

        Raises
        ------
        MissingCapabilityError
            If the plugin does not support connection validation.
        """
        if not self.is_capable_of(VALIDATION_CONNECTION):
            raise utils.create_error(MissingCapabilityError(VALIDATION_CONNECTION))
        raise utils.create_error(
            NotImplementedError(f"test_connection not implemented by {self.manifest().id}")
        )

    # TODO: find way to type hint the DataFrame to make plugin development smoother?

    def list_schemas(self) -> pl.DataFrame:
        """
        List all schemas (databases, file systems, containers) in the data source.

        Returns
        -------
        pl.DataFrame
            DataFrame with a single column 'schema' containing schema names.

        Raises
        ------
        MissingCapabilityError
            If the plugin does not support metadata operations.
        """
        if not self.is_capable_of(METADATA):
            raise utils.create_error(MissingCapabilityError(METADATA))
        raise utils.create_error(
            NotImplementedError(f"list_schemas not implemented by {self.manifest().id}")
        )

    def list_tables(self, schema: str | None = None, /) -> pl.DataFrame:
        """
        List all tables (files, paths) in the data source.

        Parameters
        ----------
        schema : str | None, optional
            The schema name to filter tables. If None, lists tables from all schemas.

        Returns
        -------
        pl.DataFrame
            DataFrame with columns:
            - schema : str
                Schema or container name
            - name : str
                Table, file, or path name
            - type : str
                Object type (e.g., 'TABLE', 'VIEW', 'FILE', 'DIRECTORY')

        Raises
        ------
        MissingCapabilityError
            If the plugin does not support metadata operations.
        """
        if not self.is_capable_of(METADATA):
            raise utils.create_error(MissingCapabilityError(METADATA))
        raise utils.create_error(
            NotImplementedError(f"list_tables not implemented by {self.manifest().id}")
        )

    def get_table_metadata(self, table: str, /, schema: str | None = None) -> TableMetadata:
        """
        Get column metadata for a specific table or file.

        Parameters
        ----------
        table : str
            The table or file name.
        schema : str | None, optional
            The schema or container name. Some data sources require this parameter.

        Returns
        -------
        pl.DataFrame
            DataFrame containing column metadata with columns:
            - COLUMN_NAME : str
                Name of the column
            - DATA_TYPE : str
                Data type of the column in source format
            - ORDINAL_POSITION : int
                1-indexed position of the column

        Raises
        ------
        MissingCapabilityError
            If the plugin does not support metadata operations.
        """
        if not self.is_capable_of(METADATA):
            raise utils.create_error(MissingCapabilityError(METADATA))
        raise utils.create_error(
            NotImplementedError(f"get_table_metadata not implemented by {self.manifest().id}")
        )

    def preview_data(
        self, table: str, /, schema: str | None = None, *, limit: int = 10
    ) -> pl.LazyFrame:
        """
        Preview data from a table or file.

        Parameters
        ----------
        table : str
            The table or file name.
        schema : str | None, optional
            The schema or container name. Some data sources require this parameter.
        limit : int, default=10
            Maximum number of rows to preview.

        Returns
        -------
        pl.LazyFrame
            Lazy DataFrame containing up to `limit` rows from the table or file.

        Raises
        ------
        NotImplementedError
            If the plugin does not implement data preview.
        """
        raise utils.create_error(
            NotImplementedError(f"preview_data not implemented by {self.manifest().id}")
        )

    @classmethod
    def is_capable_of(cls, capability: Capability, /) -> bool:
        """
        Check if the plugin supports a specific capability.

        Parameters
        ----------
        capability : Capability
            The capability to check for.

        Returns
        -------
        bool
            True if the plugin supports the capability, False otherwise.
        """
        return capability in cls.manifest().capabilities

    @classmethod
    def validate_connection(
        cls, data_source: DataSource, /, data_source_type: DataSourceType
    ) -> Exception | None:
        """
        Validate connection properties for the data source.

        Performs basic validation of required and optional properties. Subclasses
        can override this method to add plugin-specific validation logic.

        Parameters
        ----------
        data_source : DataSource
            The data source configuration to validate.
        data_source_type : DataSourceType
            The data source type definition containing required properties.

        Returns
        -------
        Exception | None
            None if validation succeeds, Exception object describing the error
            if validation fails.
        """
        ds_properties: dict[str, Any] = dict(data_source.extendedProperties)
        dst_properties: dict[str, ConnectionProperty] = {
            cp.name: cp for cp in data_source_type.connectionProperties
        }
        additional_properties: list[str] = []
        missing_properties: list[str] = []

        for prop in ds_properties:
            if prop not in dst_properties:
                additional_properties.append(prop)

        for cp in dst_properties.values():
            if cp.name not in ds_properties and cp.required and cp.default is None:
                missing_properties.append(cp.name)

        if len(additional_properties) > 0:
            logger.warning(
                f"Additional properties detected in data source '{data_source.name}': {additional_properties}"
            )

        if len(missing_properties) > 0:
            return Exception(
                f"Missing required properties in data source '{data_source.name}': {missing_properties}"
            )

        return None

    @classmethod
    @abc.abstractmethod
    def manifest(cls) -> PluginManifest:
        """
        Get the plugin manifest.

        Returns
        -------
        PluginManifest
            The plugin manifest containing metadata and capabilities.
        """
        ...

    @classmethod
    def get_ui_schema(cls) -> UiSchema:
        """
        Generate UI schema for the plugin's connection configuration.

        Builds a UI schema from the plugin's manifest, authentication modes, and
        connection properties. Used by the UI to render connection forms.

        Returns
        -------
        UiSchema
            UI schema containing authentication modes and their fields.
        """
        manifest = cls.manifest()

        ui_schema = UiSchema(
            title=manifest.displayName or manifest.id,
            authModes=[
                UiAuthMode(
                    id=auth_mode.name,
                    label=auth_mode.displayName,
                    fields=[
                        UiField(
                            key=cp.name,
                            label=cp.displayName,
                            type=cp.type.value,
                            required=cp.name in auth_mode.required,
                            default=cp.default,
                        )
                        for cp in cls.get_connection_properties()
                        if cp.name in auth_mode.required
                        or cp.name in (auth_mode.optional or [])
                        or cp.required
                    ],
                )
                for auth_mode in cls.get_auth_modes()
            ],
        )

        return ui_schema

    @staticmethod
    @abc.abstractmethod
    def create_source_location(table: str, schema: str | None = None) -> str:
        """
        Create a source location identifier for a table.

        Generates a unique identifier or path for a table within the data source.
        The format depends on the specific data source type.

        Parameters
        ----------
        table : str
            The table or file name.
        schema : str | None, optional
            The schema or container name.

        Returns
        -------
        str
            Source location identifier (e.g., "schema.table", "container/path").
        """
        ...

    @staticmethod
    @functools.lru_cache
    @abc.abstractmethod
    def get_auth_modes() -> list[AuthMode]:
        """
        Get supported authentication modes for the plugin.

        Returns
        -------
        list[AuthMode]
            List of supported authentication modes with their required and
            optional properties.
        """
        ...

    @staticmethod
    @functools.lru_cache
    @abc.abstractmethod
    def get_connection_properties() -> list[ConnectionProperty]:
        """
        Get connection properties required by the plugin.

        Returns
        -------
        list[ConnectionProperty]
            List of connection properties with their types, requirements,
            and default values.
        """
        ...

    @staticmethod
    @functools.lru_cache
    @abc.abstractmethod
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        """
        Get data type mappings from source types to target types.

        Returns
        -------
        list[SourceDataTypeMapping]
            List of mappings from source-specific data types to standardized
            target data types used by the DataM8 system.
        """
        ...
