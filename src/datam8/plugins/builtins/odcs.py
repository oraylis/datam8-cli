"""Local, offline Open Data Contract Standard v3.2.0 metadata source."""

from __future__ import annotations

import functools
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import polars as pl
import yaml
from jsonschema import Draft201909Validator
from jsonschema.protocols import Validator
from yaml.resolver import BaseResolver

from datam8 import config
from datam8.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.plugins.base import Plugin, TableMetadata
from datam8_model.data_source import (
    AuthMode,
    ConnectionProperty,
    ConnectionPropertyValueType,
    SourceDataTypeMapping,
    SourceObject,
)
from datam8_model.model import ModelEntity
from datam8_model.plugin import Capability, PluginManifest

CONTRACT_EXTENSIONS = {".yaml", ".yml", ".json"}
LOGICAL_TYPES = {
    "string": "string",
    "integer": "long",
    "number": "decimal",
    "boolean": "bit",
    "date": "date",
    "timestamp": "datetime",
    "time": "time",
    "object": "string",
    "array": "string",
    "map": "string",
    "vector": "string",
}
PHYSICAL_TYPES = {
    "string": "string",
    "text": "string",
    "varchar": "string",
    "char": "string",
    "nvarchar": "string",
    "nchar": "string",
    "boolean": "bit",
    "bool": "bit",
    "bit": "bit",
    "tinyint": "byte",
    "byte": "byte",
    "smallint": "short",
    "short": "short",
    "int": "int",
    "integer": "long",
    "bigint": "long",
    "long": "long",
    "float": "double",
    "double": "double",
    "real": "double",
    "decimal": "decimal",
    "numeric": "decimal",
    "number": "decimal",
    "date": "date",
    "time": "time",
    "timestamp": "datetime",
    "datetime": "datetime",
    "datetime2": "datetime",
    "timestamp_ntz": "datetime",
    "binary": "binary",
    "varbinary": "binary",
    "array": "string",
    "map": "string",
    "struct": "string",
    "object": "string",
    "vector": "string",
    "variant": "string",
    "json": "string",
}


class _ContractLoader(yaml.SafeLoader):
    """Keep ISO dates as strings, as required by the ODCS JSON Schema."""


_ContractLoader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in values if tag != "tag:yaml.org,2002:timestamp"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _mapping(loader: _ContractLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("Contract mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_ContractLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@functools.lru_cache(maxsize=1)
def _validator() -> Validator:
    schema = json.loads(
        files("datam8.plugins.builtins")
        .joinpath("resources/odcs-json-schema-v3.2.0.json")
        .read_text(encoding="utf-8")
    )
    return Draft201909Validator(schema)


def _literal(value: Any, *, file: Path, field: str) -> Any:
    if isinstance(value, str) and "${" in value:
        raise Datam8ValidationError(
            message=f"ODCS contract '{file}', field {field}: unresolved variable reference",
            details={"file": str(file), "field": field},
        )
    return value


class _OdcsMetadata(TableMetadata):
    """Keep ODCS import hints internal; public metadata contains source fields only."""

    def __init__(self, df, source_object, business_names, business_name):
        super().__init__(df, source_object=source_object)
        self._business_names = business_names
        self._business_name = business_name

    def apply_import_metadata(self, entity: ModelEntity) -> None:
        # Suggested technical name for the wizard; import_from_source still
        # replaces it with the explicitly selected target locator.
        entity.name = self.source_object.name
        entity.displayName = self._business_name
        for attribute in entity.attributes:
            attribute.displayName = self._business_names[attribute.name]


class OdcsFile(Plugin):
    _manifest = PluginManifest(
        id="builtin:OdcsFile",
        displayName="Local ODCS 3.2 Contract (builtin)",
        version=config.get_version(),
        entryPoint="datam8.plugins.builtins.odcs:OdcsFile",
        capabilities=[Capability.METADATA, Capability.UI_SCHEMA, Capability.VALIDATION_CONNECTION],
    )

    def _root(self) -> Path:
        cfg = self.extended_properties
        if cfg.get("protocol", "file") != "file":
            raise Datam8ValidationError(message="OdcsFile supports only protocol=file")
        raw = cfg.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise Datam8ValidationError(message="OdcsFile requires a non-empty path")
        _literal(raw, file=Path(raw), field="connection.path")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = config.solution_folder_path / path
        path = path.resolve()
        if not path.exists():
            raise Datam8NotFoundError(message=f"ODCS source '{path}' does not exist")
        if not path.is_dir() and path.suffix.lower() not in CONTRACT_EXTENSIONS:
            raise Datam8ValidationError(message=f"ODCS source '{path}' must be YAML or JSON")
        return path

    def _path(self, relative: str) -> Path:
        root = self._root()
        base = root if root.is_dir() else root.parent
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
            raise Datam8ValidationError(message="ODCS locations must stay within the source root")
        path = (base / candidate).resolve()
        if not path.is_relative_to(base) or (root.is_file() and path != root):
            raise Datam8ValidationError(message="ODCS location escapes the configured source root")
        if not path.exists():
            raise Datam8NotFoundError(message=f"ODCS location '{path}' does not exist")
        return path

    @staticmethod
    def parse_source_location(source_location: str) -> tuple[str, str]:
        path, _, name = source_location.partition("#")
        return unquote(path), unquote(name)

    def _location(self, path: Path, name: str | None = None) -> str:
        root = self._root()
        base = root if root.is_dir() else root.parent
        location = quote(path.relative_to(base).as_posix(), safe="/")
        return location if name is None else location + "#" + quote(name, safe="")

    def _load(self, path: Path) -> dict[str, Any]:
        if not path.is_file() or path.suffix.lower() not in CONTRACT_EXTENSIONS:
            raise Datam8ValidationError(
                message=f"ODCS contract '{path}' must be a YAML or JSON file"
            )
        try:
            # JSON is a YAML subset; this also rejects duplicate keys in JSON contracts.
            with path.open(encoding="utf-8-sig") as stream:
                contract = yaml.load(stream, Loader=_ContractLoader)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise Datam8ValidationError(
                message=f"Could not load ODCS contract '{path}': {error}",
                details={"file": str(path)},
            ) from error
        if not isinstance(contract, dict):
            raise Datam8ValidationError(message=f"ODCS contract '{path}' must contain an object")
        if contract.get("apiVersion") != "v3.2.0":
            raise Datam8ValidationError(
                message=f"ODCS contract '{path}', field apiVersion: expected v3.2.0"
            )
        error = next(iter(_validator().iter_errors(contract)), None)
        if error is not None:
            field = "/".join(str(part) for part in error.absolute_path) or "$"
            raise Datam8ValidationError(
                message=f"ODCS contract '{path}', field {field}: {error.message}",
                details={"file": str(path), "field": field},
            )
        names = set()
        for index, obj in enumerate(contract.get("schema", [])):
            name = _literal(obj["name"], file=path, field=f"schema/{index}/name")
            if not name or name in names:
                raise Datam8ValidationError(
                    message=f"ODCS contract '{path}', field schema/{index}/name: empty or duplicate schema name"
                )
            names.add(name)
        return contract

    def test_connection(self) -> Exception | None:
        root = self._root()
        if root.is_file():
            self._load(root)
        else:
            # Test readability without requiring every document in a folder to be a contract.
            list(root.iterdir())
        return None

    def list_source(self, source_location: str | None = None, /) -> pl.DataFrame:
        relative, name = self.parse_source_location(source_location or "")
        if name:
            raise Datam8ValidationError(
                message="Select a directory or contract file to list ODCS objects"
            )
        path = self._path(relative) if source_location else self._root()
        rows = []
        if path.is_file():
            contract = self._load(path)
            for obj in contract.get("schema", []):
                rows.append(
                    {
                        "schema": self._location(path),
                        "name": _literal(
                            obj.get("physicalName") or obj["name"],
                            file=path,
                            field=f"schema/{obj['name']}/physicalName",
                        ),
                        "object": obj["name"],
                        "type": obj.get("physicalType", "OBJECT"),
                        "description": obj.get("description"),
                        "sourceLocation": self._location(path, obj["name"]),
                    }
                )
        else:
            for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
                if child.is_dir() or child.suffix.lower() in CONTRACT_EXTENSIONS:
                    # Do not expose navigation through symlinks outside the configured root.
                    if not child.resolve().is_relative_to(self._root()):
                        continue
                    rows.append(
                        {
                            "schema": self._location(path),
                            "name": child.name,
                            "object": child.name,
                            "type": "DIRECTORY" if child.is_dir() else "CONTAINER",
                            "description": None,
                            "sourceLocation": self._location(child),
                        }
                    )
        return pl.DataFrame(
            rows,
            schema={
                "schema": pl.String,
                "name": pl.String,
                "object": pl.String,
                "type": pl.String,
                "description": pl.String,
                "sourceLocation": pl.String,
            },
        )

    def get_table_metadata(self, source_location: str, /) -> TableMetadata:
        relative, schema_name = self.parse_source_location(source_location)
        if not relative or not schema_name:
            raise Datam8ValidationError(
                message="ODCS metadata requires <relative-file>#<schema-name>"
            )
        path = self._path(relative)
        contract = self._load(path)
        selected = next(
            (obj for obj in contract.get("schema", []) if obj["name"] == schema_name), None
        )
        if selected is None:
            raise Datam8NotFoundError(
                message=f"ODCS contract '{path}' has no schema '{schema_name}'"
            )
        if not selected.get("properties"):
            raise Datam8ValidationError(
                message=f"ODCS schema '{schema_name}' in '{path}' has no importable columns"
            )
        rows = []
        names = set()
        business_names = {}
        for index, prop in enumerate(selected["properties"]):
            prefix = f"schema/{schema_name}/properties/{index}"
            # Only consumed metadata must be literal. Advisory sections can contain variables.
            for field in (
                "name",
                "physicalName",
                "businessName",
                "description",
                "physicalType",
                "logicalType",
            ):
                _literal(prop.get(field), file=path, field=f"{prefix}/{field}")
            name = prop.get("physicalName") or prop["name"]
            if not name or name in names:
                raise Datam8ValidationError(
                    message=f"ODCS contract '{path}', field {prefix}/name: duplicate or empty column name"
                )
            names.add(name)
            physical = prop.get("physicalType")
            logical = prop.get("logicalType")
            options = prop.get("logicalTypeOptions", {})
            if not physical and not logical:
                raise Datam8ValidationError(
                    message=f"ODCS contract '{path}', field {prefix}: physicalType or logicalType is required for import"
                )
            physical_text = (physical or "").strip()
            length = re.fullmatch(r"(?:n?varchar|n?char)\s*\((\d+)\)", physical_text, re.I)
            decimal = re.fullmatch(
                r"(?:decimal|numeric|number)\s*\((\d+)\s*(?:,\s*(\d+))?\)", physical_text, re.I
            )
            max_length = options.get("maxLength") if logical == "string" else None
            if max_length is None and length:
                max_length = int(length[1])
            precision = int(decimal[1]) if decimal else None
            scale = int(decimal[2] or 0) if decimal else None
            # ODCS permits maxLength=0, while DataM8 only permits positive charLen.
            if max_length == 0:
                raise Datam8ValidationError(
                    message=f"ODCS contract '{path}', field {prefix}/logicalTypeOptions/maxLength: DataM8 requires a positive length"
                )
            business_names[name] = prop.get("businessName")
            rows.append(
                {
                    "name": name,
                    "ordinal": index + 1,
                    "dataType": physical or logical,
                    "description": prop.get("description"),
                    "isNullable": not prop.get("required", False),
                    "isPrimaryKey": prop.get("primaryKey", False),
                    "maxLength": max_length,
                    "numericPrecision": precision,
                    "numericScale": scale,
                }
            )
        for field in ("physicalName", "businessName", "description", "physicalType"):
            _literal(selected.get(field), file=path, field=f"schema/{schema_name}/{field}")
        return _OdcsMetadata(
            pl.DataFrame(
                rows,
                schema_overrides={
                    "maxLength": pl.Int64,
                    "numericPrecision": pl.Int64,
                    "numericScale": pl.Int64,
                    "description": pl.String,
                },
            ),
            SourceObject(
                name=selected.get("physicalName") or selected["name"],
                type=selected.get("physicalType", "OBJECT"),
                description=selected.get("description"),
            ),
            business_names,
            selected.get("businessName"),
        )

    def get_sources(self, source_location: str, /) -> list[dict[str, Any]]:
        """Opt into the existing import-description path for this contract object."""
        metadata = self.get_table_metadata(source_location)
        return [
            {
                "sourceLocation": source_location,
                "sourceName": field.name,
                "targetName": field.name,
                "sourceDataType": {
                    "type": field.dataType,
                    "nullable": field.isNullable,
                    "charLen": field.maxLength,
                    "precision": field.numericPrecision,
                    "scale": field.numbericScale,
                },
            }
            for field in metadata.iter_source_fields()
        ]

    @classmethod
    def resolve_source_type(cls, source_type: str, /) -> str:
        match = re.match(r"^[a-z_]+", source_type.strip().lower())
        if not match or match[0] not in PHYSICAL_TYPES:
            raise ValueError(f"Unsupported ODCS physical type: {source_type}")
        return PHYSICAL_TYPES[match[0]]

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls._manifest

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_auth_modes() -> list[AuthMode]:
        return [
            AuthMode(
                name="no_auth",
                displayName="Local file / no authentication",
                required=["path"],
                optional=["protocol"],
            )
        ]

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_connection_properties() -> list[ConnectionProperty]:
        return [
            ConnectionProperty(
                name="path",
                displayName="Contract file or directory",
                required=True,
                type=ConnectionPropertyValueType.STRING,
            ),
            ConnectionProperty(
                name="protocol",
                displayName="Protocol",
                required=False,
                type=ConnectionPropertyValueType.STRING,
                default="file",
            ),
        ]

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        return [
            SourceDataTypeMapping(sourceType=source, targetType=target)
            for source, target in {**LOGICAL_TYPES, **PHYSICAL_TYPES}.items()
        ]
