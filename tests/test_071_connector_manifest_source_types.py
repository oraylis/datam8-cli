from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CONNECTORS_ROOT = REPO_ROOT / "plugins-python" / "connectors"

if not CONNECTORS_ROOT.exists():
    pytest.skip("Connector manifests are not available in this repository layout.", allow_module_level=True)


EXPECTED_SOURCE_TYPES: dict[str, set[str]] = {
    "adls": {"string"},
    "s3": {"string"},
    "http-api": {"string", "double", "boolean"},
    "databricks-uc": {
        "string",
        "char",
        "varchar",
        "boolean",
        "tinyint",
        "smallint",
        "int",
        "bigint",
        "float",
        "double",
        "decimal",
        "date",
        "timestamp",
        "timestamp_ntz",
        "binary",
        "array",
        "map",
        "struct",
    },
    "fabric": {
        "string",
        "char",
        "varchar",
        "boolean",
        "tinyint",
        "smallint",
        "int",
        "bigint",
        "float",
        "double",
        "decimal",
        "date",
        "timestamp",
        "timestamp_ntz",
        "binary",
        "array",
        "map",
        "struct",
    },
    "sqlserver": {
        "bigint",
        "binary",
        "bit",
        "char",
        "date",
        "datetime",
        "datetime2",
        "datetimeoffset",
        "decimal",
        "float",
        "image",
        "int",
        "money",
        "nchar",
        "ntext",
        "numeric",
        "nvarchar",
        "real",
        "smalldatetime",
        "smallint",
        "smallmoney",
        "text",
        "time",
        "timestamp",
        "tinyint",
        "uniqueidentifier",
        "varbinary",
        "varchar",
        "xml",
        "sql_variant",
    },
    "mysql": {
        "tinyint",
        "smallint",
        "mediumint",
        "int",
        "bigint",
        "decimal",
        "float",
        "double",
        "bit",
        "char",
        "varchar",
        "binary",
        "varbinary",
        "tinytext",
        "text",
        "mediumtext",
        "longtext",
        "tinyblob",
        "blob",
        "mediumblob",
        "longblob",
        "date",
        "datetime",
        "timestamp",
        "time",
        "year",
        "json",
        "enum",
        "set",
    },
    "postgresql": {
        "smallint",
        "integer",
        "bigint",
        "numeric",
        "real",
        "double precision",
        "character varying",
        "character",
        "text",
        "boolean",
        "date",
        "time without time zone",
        "time with time zone",
        "timestamp without time zone",
        "timestamp with time zone",
        "interval",
        "bytea",
        "uuid",
        "json",
        "jsonb",
        "xml",
        "ARRAY",
        "USER-DEFINED",
    },
    "oracle": {
        "VARCHAR2",
        "NVARCHAR2",
        "CHAR",
        "NCHAR",
        "CLOB",
        "NCLOB",
        "LONG",
        "NUMBER",
        "FLOAT",
        "BINARY_FLOAT",
        "BINARY_DOUBLE",
        "DATE",
        "TIMESTAMP",
        "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP WITH LOCAL TIME ZONE",
        "INTERVAL YEAR TO MONTH",
        "INTERVAL DAY TO SECOND",
        "RAW",
        "LONG RAW",
        "BLOB",
        "XMLTYPE",
        "ROWID",
        "UROWID",
    },
}


@pytest.mark.parametrize("connector_id", sorted(EXPECTED_SOURCE_TYPES))
def test_connector_manifest_source_types_are_connector_specific(connector_id: str) -> None:
    plugin_json_path = CONNECTORS_ROOT / connector_id / "plugin.json"
    payload = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    mapping = payload.get("dataTypeMapping")
    assert isinstance(mapping, list), f"{connector_id}: dataTypeMapping must be a list"

    source_types: list[str] = []
    normalized: set[str] = set()
    for row in mapping:
        assert isinstance(row, dict), f"{connector_id}: mapping rows must be objects"
        source = row.get("sourceType")
        target = row.get("targetType")
        assert isinstance(source, str) and source.strip(), f"{connector_id}: sourceType must be non-empty"
        assert isinstance(target, str) and target.strip(), f"{connector_id}: targetType must be non-empty"
        source_trimmed = source.strip()
        source_types.append(source_trimmed)
        lowered = source_trimmed.lower()
        assert lowered not in normalized, f"{connector_id}: duplicate sourceType '{source_trimmed}'"
        normalized.add(lowered)

    assert set(source_types) == EXPECTED_SOURCE_TYPES[connector_id], (
        f"{connector_id}: sourceType set differs from expected connector-specific set"
    )
