"""Builtin Unity Catalog metadata and SQL preview connector.

Adapted from ORAYLIS datam8-plugins/plugins/databricks_uc (1.1.0).
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import polars as pl

from datam8 import config
from datam8.plugins.base import Plugin, TableMetadata
from datam8_model.data_source import (
    AuthMode,
    ConnectionProperty,
    DataSource,
    DataSourceType,
    SourceDataTypeMapping,
    SourceObject,
)
from datam8_model.plugin import PluginManifest

MANIFEST = {
    "id": "builtin:DatabricksUnityCatalog",
    "displayName": "Databricks Unity Catalog",
    "version": config.get_version(),
    "entryPoint": "datam8.plugins.builtins.databricks_uc:DatabricksUnityCatalog",
    "capabilities": ["uiSchema", "metadata", "validationConnection", "previewData"],
}

# Required common fields are included by Plugin.get_ui_schema in every mode.
CONNECTION_PROPERTIES = [
    {
        "name": "authMode",
        "displayName": "Authentication",
        "type": "string",
        "required": True,
        "default": "pat",
    },
    {
        "name": "workspace_url",
        "displayName": "Workspace URL",
        "type": "string",
        "required": True,
    },
    {
        "name": "catalog",
        "displayName": "Catalog filter",
        "type": "string",
        "required": False,
    },
    {
        "name": "schema",
        "displayName": "Schema filter",
        "type": "string",
        "required": False,
    },
    {
        "name": "warehouse_id",
        "displayName": "SQL Warehouse ID (preview)",
        "type": "string",
        "required": False,
    },
    {
        "name": "http_path",
        "displayName": "SQL Warehouse HTTP path (alternative)",
        "type": "string",
        "required": False,
    },
    {
        "name": "token",
        "displayName": "Developer token (PAT)",
        "type": "secret",
        "required": False,
    },
    {
        "name": "client_id",
        "displayName": "Client ID",
        "type": "string",
        "required": False,
    },
    {
        "name": "client_secret",
        "displayName": "Client secret",
        "type": "secret",
        "required": False,
    },
    {
        "name": "tenant_id",
        "displayName": "Microsoft Entra tenant ID",
        "type": "string",
        "required": False,
    },
    {
        "name": "auth_scope",
        "displayName": "Databricks OAuth scope",
        "type": "string",
        "required": False,
        "default": "all-apis",
    },
]
COMMON_OPTIONAL = ["catalog", "schema", "warehouse_id", "http_path"]
AUTH_MODES = [
    {
        "name": "pat",
        "displayName": "Developer token (PAT)",
        "required": ["workspace_url", "token"],
        "optional": COMMON_OPTIONAL,
    },
    {
        "name": "oauthClientCredentials",
        "displayName": "Service Principal (Databricks OAuth)",
        "required": ["workspace_url", "client_id", "client_secret"],
        "optional": [*COMMON_OPTIONAL, "auth_scope"],
    },
    {
        "name": "azureServicePrincipal",
        "displayName": "Service Principal (Azure Entra)",
        "required": ["workspace_url", "tenant_id", "client_id", "client_secret"],
        "optional": COMMON_OPTIONAL,
    },
]
TYPE_MAP = {
    "string": "string",
    "char": "string",
    "varchar": "string",
    "boolean": "bit",
    "bool": "bit",
    "tinyint": "byte",
    "byte": "byte",
    "smallint": "short",
    "short": "short",
    "int": "int",
    "integer": "int",
    "bigint": "long",
    "long": "long",
    "float": "double",
    "double": "double",
    "decimal": "decimal",
    "numeric": "decimal",
    "date": "date",
    "timestamp": "datetime",
    "timestamp_ntz": "datetime",
    "binary": "binary",
    "array": "string",
    "map": "string",
    "struct": "string",
    "variant": "string",
    "interval": "string",
    "null": "string",
    "void": "string",
}
DATA_TYPE_MAPPINGS = [
    {"sourceType": source, "targetType": target} for source, target in TYPE_MAP.items()
]
PREVIEW_TIMEOUT_SECONDS = 30


class _PreviewTimeout(RuntimeError):
    def __init__(self):
        super().__init__(
            "Data preview could not complete within its 30-second time budget or was canceled; "
            "start the SQL Warehouse and retry"
        )


def _request_timeout(timeout: float, deadline: float | None) -> float:
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _PreviewTimeout()
    return min(timeout, remaining)


def _read_response(response, timeout: float, deadline: float | None) -> bytes:
    if deadline is None:
        return response.read()
    chunks = []
    while True:
        remaining = _request_timeout(timeout, deadline)
        # urllib has already consumed part of the budget while connecting and
        # reading headers. Shrink the body timeout before each socket read.
        raw = getattr(getattr(response, "fp", None), "raw", None)
        sock = getattr(raw, "_sock", None)
        if sock is not None:
            sock.settimeout(remaining)
        chunk = response.read1(64 * 1024)
        _request_timeout(timeout, deadline)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _workspace_url(value: Any) -> str:
    raw = str(value or "").strip().rstrip("/")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
    ):
        raise ValueError("workspace_url must be a workspace host or HTTPS origin")
    if parsed.scheme != "https" and parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("workspace_url requires HTTPS (HTTP is allowed only for local tests)")
    return raw


def _warehouse_id(config: dict[str, Any], *, required: bool = False) -> str:
    warehouse = str(config.get("warehouse_id") or "").strip()
    path = str(config.get("http_path") or "").strip()
    if warehouse and not re.fullmatch(r"[A-Za-z0-9_-]+", warehouse):
        raise ValueError("warehouse_id must be a SQL Warehouse ID")
    if path:
        match = re.fullmatch(r"/?sql/1\.0/warehouses/([A-Za-z0-9_-]+)/?", path)
        if not match:
            raise ValueError("http_path must have the form /sql/1.0/warehouses/<warehouse-id>")
        if warehouse and warehouse != match[1]:
            raise ValueError("warehouse_id and http_path identify different warehouses")
        warehouse = match[1]
    if required and not warehouse:
        raise ValueError("Data preview requires warehouse_id or a SQL Warehouse http_path")
    return warehouse


def validate_connection(ds: DataSource, dst=None, cps=None) -> Exception | None:
    """Validate configuration without resolving secrets or contacting the workspace."""
    try:
        config = dict(ds.extendedProperties or {})
        mode = str(config.get("authMode") or "pat").strip()
        auth = next((item for item in AUTH_MODES if item["name"] == mode), None)
        if auth is None:
            raise ValueError(
                "Unsupported authMode; use pat, oauthClientCredentials or azureServicePrincipal"
            )
        for key in ["workspace_url", *auth["required"]]:
            value = config.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Missing required connection property: {key}")
        for key in ["token"] if mode == "pat" else ["client_secret"]:
            secret_ref = config.get(key)
            if (
                not isinstance(secret_ref, str)
                or not secret_ref.startswith("ref://")
                or not secret_ref[6:].strip()
            ):
                raise ValueError(
                    f"{key} must be a ref:// secret reference; save the secret in DataM8"
                )
        _workspace_url(config["workspace_url"])
        _warehouse_id(config)
        if mode == "azureServicePrincipal" and not re.fullmatch(
            r"[A-Za-z0-9.-]+", str(config["tenant_id"])
        ):
            raise ValueError("tenant_id must be a tenant UUID or verified tenant domain")
        return None
    except (ValueError, TypeError) as error:
        return error


def _quoted_name(parts: tuple[str, ...]) -> str:
    return ".".join("`" + part.replace("`", "``") + "`" for part in parts)


def _handle(parts: tuple[str, str, str]) -> str:
    catalog, schema, table = parts
    return f"[{catalog}.{schema}].[{table.replace(']', ']]')}]"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send bearer/client credentials to an unexpected redirect target.
        return None


class DatabricksUnityCatalog(Plugin):
    _manifest = PluginManifest.model_validate(MANIFEST)
    # The host creates a plugin per request. Share tokens between these instances,
    # keyed by a credential digest, without retaining raw client secrets here.
    _tokens: dict[str, tuple[str, float]] = {}
    _token_lock = threading.Lock()

    def __init__(
        self,
        manifest: PluginManifest,
        data_source: DataSource,
        data_source_type: DataSourceType,
    ):
        super().__init__(manifest, data_source, data_source_type)
        error = self.validate_connection(data_source, data_source_type)
        if error:
            raise error
        self._opener = urllib.request.build_opener(_NoRedirect())

    @classmethod
    def manifest(cls) -> PluginManifest:
        return cls._manifest

    @classmethod
    def validate_connection(
        cls, data_source: DataSource, /, data_source_type: DataSourceType
    ) -> Exception | None:
        return validate_connection(data_source, data_source_type)

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_auth_modes() -> list[AuthMode]:
        return [AuthMode.model_validate(mode) for mode in AUTH_MODES]

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_connection_properties() -> list[ConnectionProperty]:
        return [ConnectionProperty.model_validate(prop) for prop in CONNECTION_PROPERTIES]

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_data_type_mappings() -> list[SourceDataTypeMapping]:
        return [SourceDataTypeMapping(**mapping) for mapping in DATA_TYPE_MAPPINGS]

    @classmethod
    def resolve_source_type(cls, source_type: str, /) -> str:
        match = re.match(r"^[a-z_]+", source_type.strip().lower())
        kind = match[0] if match else ""
        if kind not in TYPE_MAP:
            raise ValueError(
                "Unsupported Unity Catalog column type; add an explicit connector type mapping"
            )
        return TYPE_MAP[kind]

    @staticmethod
    def parse_source_location(source_location: str) -> tuple[str, ...]:
        raw = source_location.strip()
        parts = []
        while raw:
            if raw[0] in "[`":
                end = "]" if raw[0] == "[" else "`"
                pattern = r"\[((?:[^\]]|\]\])*)\]" if end == "]" else r"`((?:[^`]|``)*)`"
                match = re.match(pattern, raw)
                if not match:
                    raise ValueError("Invalid quoted Unity Catalog source location")
                part = match[1].replace(end * 2, end)
                raw = raw[match.end() :].strip()
            else:
                part, _, rest = raw.partition(".")
                part = part.strip()
                raw = "." + rest if "." in raw else ""
                if any(char in part for char in "[]`"):
                    raise ValueError("Invalid Unity Catalog source location")
            if not part:
                raise ValueError("Source location contains an empty identifier")
            parts.append(part)
            if raw:
                if not raw.startswith(".") or not raw[1:].strip():
                    raise ValueError("Invalid Unity Catalog source location separator")
                raw = raw[1:].strip()
        # beta.6 stores catalog.schema as its single SQL-style schema component.
        if len(parts) == 2 and "." in parts[0]:
            parts = [*parts[0].split("."), parts[1]]
        if len(parts) not in {2, 3}:
            raise ValueError("Use catalog.schema or catalog.schema.table as source location")
        return tuple(parts)

    def _location(self, location: str, *, table: bool) -> tuple[str, ...]:
        parts = self.parse_source_location(location)
        if len(parts) != (3 if table else 2):
            raise ValueError(
                "A fully qualified table location is required"
                if table
                else "A catalog.schema location is required"
            )
        return parts

    def _transport(
        self, url: str, *, method="GET", headers=None, body=None, timeout=20, deadline=None
    ) -> dict:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with self._opener.open(
                request, timeout=_request_timeout(timeout, deadline)
            ) as response:
                raw = _read_response(response, timeout, deadline)
            _request_timeout(timeout, deadline)
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            _request_timeout(timeout, deadline)
            return payload
        except urllib.error.HTTPError as error:
            reasons = {
                400: "Invalid request; check connection configuration",
                401: "Authentication failed; check the token or Service Principal credentials",
                403: "Access denied; check workspace, Unity Catalog and SQL Warehouse permissions",
                404: "Requested catalog, schema, table or warehouse was not found",
                429: "Databricks rate limit reached; retry later",
            }
            message = reasons.get(error.code, "Databricks request failed")
            raise RuntimeError(f"{message} (HTTP {error.code})") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            _request_timeout(timeout, deadline)
            raise RuntimeError(
                "Databricks connection failed or timed out; check workspace URL and network access"
            ) from None
        except (ValueError, UnicodeError):
            raise RuntimeError("Databricks returned an invalid JSON response") from None

    def _entra_token_url(self, tenant: str) -> str:
        return f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0/token"

    def _access_token(self, *, deadline: float | None = None) -> str:
        cfg = self.extended_properties
        mode = str(cfg.get("authMode") or "pat").strip()
        if mode == "pat":
            token = str(cfg["token"]).strip()
            if not token:
                raise ValueError("The resolved PAT is empty")
            return token
        values = [
            mode,
            _workspace_url(cfg["workspace_url"]),
            cfg.get("tenant_id"),
            cfg["client_id"],
            cfg["client_secret"],
            cfg.get("auth_scope"),
        ]
        key = hashlib.sha256(json.dumps(values).encode()).hexdigest()
        lock_timeout = (
            -1 if deadline is None else _request_timeout(PREVIEW_TIMEOUT_SECONDS, deadline)
        )
        if not self._token_lock.acquire(timeout=lock_timeout):
            raise _PreviewTimeout()
        try:
            now = time.monotonic()
            cached = self._tokens.get(key)
            if cached and cached[1] > now:
                return cached[0]
            form = {"grant_type": "client_credentials"}
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
            if mode == "oauthClientCredentials":
                url = _workspace_url(cfg["workspace_url"]) + "/oidc/v1/token"
                form["scope"] = str(cfg.get("auth_scope") or "all-apis")
                credentials = f"{cfg['client_id']}:{cfg['client_secret']}".encode()
                headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode()
            else:
                url = self._entra_token_url(cfg["tenant_id"])
                form.update(
                    client_id=cfg["client_id"],
                    client_secret=cfg["client_secret"],
                    scope="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default",
                )
            payload = self._transport(
                url,
                method="POST",
                headers=headers,
                body=urllib.parse.urlencode(form).encode(),
                deadline=deadline,
            )
            _request_timeout(PREVIEW_TIMEOUT_SECONDS, deadline)
            token = payload.get("access_token")
            try:
                expiry = float(payload["expires_in"])
            except (KeyError, TypeError, ValueError):
                raise RuntimeError("Token response is missing a valid expires_in") from None
            if not isinstance(token, str) or not token.strip() or expiry <= 0:
                raise RuntimeError("Token response is missing a valid access token or expiry")
            # Limit retained tokens and renew 60 seconds before expiry.
            for old_key, (_, expires) in list(self._tokens.items()):
                if expires <= now:
                    del self._tokens[old_key]
            if len(self._tokens) >= 128:
                self._tokens.pop(next(iter(self._tokens)))
            self._tokens[key] = (token, time.monotonic() + max(0, expiry - 60))
            return token
        finally:
            self._token_lock.release()

    def _request(
        self, path: str, *, params=None, method="GET", data=None, timeout=20, deadline=None
    ) -> dict:
        _request_timeout(timeout, deadline)
        url = _workspace_url(self.extended_properties["workspace_url"]) + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Authorization": "Bearer " + self._access_token(deadline=deadline),
            "Accept": "application/json",
        }
        body = None
        if data is not None:
            if deadline is not None and "wait_timeout" in data:
                # Databricks permits synchronous waits of 5–50 seconds. Do not
                # submit asynchronously when there is insufficient budget left.
                wait_seconds = int(_request_timeout(PREVIEW_TIMEOUT_SECONDS, deadline))
                if wait_seconds < 5:
                    raise _PreviewTimeout()
                data = {**data, "wait_timeout": f"{wait_seconds}s"}
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        payload = self._transport(
            url, method=method, headers=headers, body=body, timeout=timeout, deadline=deadline
        )
        _request_timeout(timeout, deadline)
        return payload

    def _pages(self, kind: str, params=None) -> list[dict]:
        query = {"max_results": 1000, **(params or {})}
        rows = []
        seen = set()
        while True:
            payload = self._request("/api/2.1/unity-catalog/" + kind, params=query)
            rows.extend(payload.get(kind) or [])
            token = payload.get("next_page_token")
            if not token:
                return rows
            if token in seen:
                raise RuntimeError("Databricks returned a repeated pagination token")
            seen.add(token)
            query["page_token"] = token

    def test_connection(self) -> Exception | None:
        self.list_source()
        return None

    def list_source(self, source_location: str | None = None, /) -> pl.DataFrame:
        return self.list_tables(source_location) if source_location else self.list_schemas()

    def list_schemas(self) -> pl.DataFrame:
        cfg = self.extended_properties
        catalogs = [{"name": cfg["catalog"]}] if cfg.get("catalog") else self._pages("catalogs")
        rows = []
        for catalog in catalogs:
            name = catalog["name"]
            for schema in self._pages("schemas", {"catalog_name": name}):
                if cfg.get("schema") and schema["name"] != cfg["schema"]:
                    continue
                location = f"{name}.{schema['name']}"
                rows.append({"schema": location, "type": "SCHEMA", "sourceLocation": location})
        return pl.DataFrame(
            rows,
            schema={
                "schema": pl.String,
                "type": pl.String,
                "sourceLocation": pl.String,
            },
        )

    def list_tables(self, schema: str | None = None) -> pl.DataFrame:
        cfg = self.extended_properties
        location = schema or f"{cfg.get('catalog', '')}.{cfg.get('schema', '')}"
        catalog, schema_name = self._location(location, table=False)
        rows = []
        for item in self._pages("tables", {"catalog_name": catalog, "schema_name": schema_name}):
            parts = (catalog, schema_name, item["name"])
            rows.append(
                {
                    "schema": f"{catalog}.{schema_name}",
                    "name": item["name"],
                    "type": item.get("table_type", "TABLE"),
                    "description": item.get("comment"),
                    "sourceLocation": _handle(parts),
                    "sourceOverride": {"sourceLocation": _quoted_name(parts)},
                }
            )
        if not rows:
            return pl.DataFrame(
                schema={
                    "schema": pl.String,
                    "name": pl.String,
                    "type": pl.String,
                    "sourceLocation": pl.String,
                }
            )
        return pl.DataFrame(rows)

    def get_table_metadata(self, source_location: str, /) -> TableMetadata:
        parts = self._location(source_location, table=True)
        full_name = urllib.parse.quote(".".join(parts), safe="")
        payload = self._request("/api/2.1/unity-catalog/tables/" + full_name)
        columns = payload.get("columns") or []
        if not columns:
            raise ValueError(
                "Unity Catalog returned no column metadata; check table existence and metadata permissions"
            )
        primary_keys = {
            name
            for constraint in payload.get("table_constraints") or []
            for name in (constraint.get("primary_key_constraint") or {}).get("child_columns", [])
        }
        rows = []
        columns = sorted(columns, key=lambda col: col.get("position", 0))
        for index, column in enumerate(columns):
            source_type = str(column.get("type_text") or column.get("type_name") or "")
            type_text = source_type.strip()
            size = re.fullmatch(r"(?:varchar|char)\((\d+)\)", type_text, re.IGNORECASE)
            decimal = re.fullmatch(
                r"(?:decimal|numeric)\((\d+)\s*,\s*(\d+)\)", type_text, re.IGNORECASE
            )
            precision = column.get("type_precision") or (int(decimal[1]) if decimal else None)
            scale = column.get("type_scale")
            if scale is None and decimal:
                scale = int(decimal[2])
            is_decimal = type_text.lower().startswith(("decimal", "numeric"))
            rows.append(
                {
                    "name": column["name"],
                    "ordinal": int(column.get("position", index)) + 1,
                    "dataType": source_type,
                    "isNullable": column.get("nullable", True),
                    "description": column.get("comment"),
                    "isPrimaryKey": column["name"] in primary_keys,
                    "maxLength": int(size[1]) if size else None,
                    "numericPrecision": precision if is_decimal else None,
                    "numericScale": scale if is_decimal else None,
                }
            )
        return TableMetadata(
            pl.DataFrame(rows),
            SourceObject(
                schema=f"{parts[0]}.{parts[1]}",
                name=parts[2],
                type=payload.get("table_type", "TABLE"),
                description=payload.get("comment"),
                sourceOverride={"sourceLocation": _quoted_name(parts)},
            ),
        )

    def get_sources(self, source_location: str, /) -> list[dict[str, Any]]:
        """Use the quoted table location for both metadata and data reads."""
        physical_location = _quoted_name(self._location(source_location, table=True))
        metadata = self.get_table_metadata(source_location)
        return [
            {
                "sourceLocation": physical_location,
                "metadataLocation": None,
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

    def get_source_capabilities(self) -> dict[str, bool]:
        capabilities = super().get_source_capabilities()
        capabilities["previewData"] = bool(_warehouse_id(self.extended_properties))
        return capabilities

    def preview_data(self, source_location: str, *, limit: int = 10) -> pl.LazyFrame:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Preview limit must be an integer between 1 and 1000")
        deadline = time.monotonic() + PREVIEW_TIMEOUT_SECONDS
        warehouse = _warehouse_id(self.extended_properties, required=True)
        parts = self._location(source_location, table=True)
        payload = self._request(
            "/api/2.0/sql/statements",
            method="POST",
            timeout=PREVIEW_TIMEOUT_SECONDS,
            deadline=deadline,
            data={
                "warehouse_id": warehouse,
                "statement": f"SELECT * FROM {_quoted_name(parts)} LIMIT {limit}",
                "row_limit": limit,
                "byte_limit": 1024 * 1024,
                "format": "JSON_ARRAY",
                "disposition": "INLINE",
                "wait_timeout": "30s",
                "on_wait_timeout": "CANCEL",
            },
        )
        state = payload.get("status", {}).get("state")
        if state != "SUCCEEDED":
            if state in {"PENDING", "RUNNING"} and payload.get("statement_id"):
                statement_id = urllib.parse.quote(payload["statement_id"], safe="")
                try:
                    self._request(
                        f"/api/2.0/sql/statements/{statement_id}/cancel",
                        method="POST",
                        deadline=deadline,
                    )
                except RuntimeError:
                    # Best effort within the original budget; cleanup errors
                    # must not hide the preview timeout or add another wait.
                    pass
            if state in {"PENDING", "RUNNING", "CANCELED"}:
                raise _PreviewTimeout()
            raise RuntimeError(
                "SQL preview failed; check SELECT privileges, SQL Warehouse access and table availability"
            )
        names = [
            column["name"]
            for column in payload.get("manifest", {}).get("schema", {}).get("columns", [])
        ]
        if not names or len(names) != len(set(names)):
            raise RuntimeError("SQL preview returned an invalid result schema")
        result = payload.get("result") or {}
        rows = list(result.get("data_array") or [])
        seen = set()
        while len(rows) < limit and result.get("next_chunk_index") is not None:
            index = result["next_chunk_index"]
            if not isinstance(index, int) or index < 0 or index in seen:
                raise RuntimeError("SQL preview returned an invalid chunk index")
            seen.add(index)
            statement_id = urllib.parse.quote(payload["statement_id"], safe="")
            result = self._request(
                f"/api/2.0/sql/statements/{statement_id}/result/chunks/{index}", deadline=deadline
            )
            rows.extend(result.get("data_array") or [])
        if any(len(row) != len(names) for row in rows):
            raise RuntimeError("SQL preview returned rows that do not match its result schema")
        # JSON_ARRAY preserves nulls; values are display strings as returned by Databricks.
        frame = pl.DataFrame(
            rows[:limit], schema={name: pl.String for name in names}, orient="row"
        ).lazy()
        _request_timeout(PREVIEW_TIMEOUT_SECONDS, deadline)
        return frame
