from __future__ import annotations

from typing import Any

from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8PermissionError,
    Datam8ValidationError,
)


class SqlServerMetadataConnector:
    def __init__(
        self,
        *,
        server: str,
        port: int,
        database: str,
        user: str,
        password: str,
        encrypt: bool = True,
        trust_server_certificate: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.server = server
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.encrypt = bool(encrypt)
        self.trust_server_certificate = bool(trust_server_certificate)
        self.timeout_seconds = timeout_seconds

    def _connect(self):
        try:
            try:
                import pytds  # type: ignore
            except Exception as e:
                raise Datam8ExternalSystemError(
                    code="missing_dependency",
                    message="SQL Server connector dependency is missing (python-tds).",
                    details={"error": str(e)},
                    hint="Install dependencies and restart: pip install python-tds",
                )

            import certifi

            cafile = None
            if self.encrypt:
                cafile = __import__("os").environ.get("DATAM8_SQLSERVER_CAFILE") or certifi.where()
            return pytds.connect(
                dsn=self.server,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                timeout=self.timeout_seconds,
                login_timeout=self.timeout_seconds,
                autocommit=True,
                cafile=cafile,
                validate_host=not self.trust_server_certificate,
                enc_login_only=not self.encrypt,
            )
        except Exception as e:
            if isinstance(e, (Datam8ExternalSystemError, Datam8PermissionError, Datam8ValidationError)):
                raise
            msg = str(e).lower()
            if "pyopenssl" in msg and ("does not work" in msg or "install" in msg):
                raise Datam8ExternalSystemError(
                    code="sqlserver_error",
                    message="SQL Server connection failed (TLS support missing).",
                    details={"error": str(e)},
                    hint="Install pyOpenSSL (and restart): pip install pyOpenSSL",
                )
            if "login failed" in msg or "authentication" in msg or "denied" in msg:
                raise Datam8PermissionError(code="auth", message="Authentication failed.", details={"error": str(e)})
            raise Datam8ExternalSystemError(code="sqlserver_error", message="SQL Server connection failed.", details={"error": str(e)})

    def test_connection(self) -> dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
        return {"ok": True}

    def list_schemas(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME")
            rows = cur.fetchall()
            return [{"name": r[0]} for r in (rows or [])]

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        schema_filter = (schema or "").strip() or None
        with self._connect() as conn:
            cur = conn.cursor()
            if schema_filter:
                cur.execute(
                    """SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA=%s AND TABLE_TYPE IN ('BASE TABLE','VIEW')
                    ORDER BY TABLE_SCHEMA, TABLE_NAME""",
                    (schema_filter,),
                )
            else:
                cur.execute(
                    """SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE IN ('BASE TABLE','VIEW')
                    ORDER BY TABLE_SCHEMA, TABLE_NAME"""
                )
            rows = cur.fetchall()
            out = []
            for r in rows:
                schema, name, typ = r[0], r[1], r[2]
                out.append({"schema": schema, "name": name, "type": typ})
            return out

    def get_table_metadata(self, *, schema: str, table: str) -> dict[str, Any]:
        schema = schema or "dbo"
        if not table:
            raise Datam8ValidationError(message="table is required", details=None)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s""",
                (schema, table),
            )
            row = cur.fetchone()
            if not row:
                raise Datam8ValidationError(message="Table not found.", details={"schema": schema, "table": table})
            table_type = row[0]

            cur.execute(
                """SELECT COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                       NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                ORDER BY ORDINAL_POSITION""",
                (schema, table),
            )
            cols = cur.fetchall()

            cur.execute(
                """SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                 AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                  AND tc.TABLE_SCHEMA=%s AND tc.TABLE_NAME=%s""",
                (schema, table),
            )
            pk_cols = {r[0] for r in cur.fetchall()}

            columns = []
            for c in cols:
                name = c[0]
                columns.append(
                    {
                        "name": name,
                        "ordinal": int(c[1]),
                        "dataType": str(c[2]),
                        "maxLength": int(c[3]) if c[3] is not None else None,
                        "numericPrecision": int(c[4]) if c[4] is not None else None,
                        "numericScale": int(c[5]) if c[5] is not None else None,
                        "isNullable": str(c[6]).upper() == "YES",
                        "isPrimaryKey": name in pk_cols,
                    }
                )

            return {"schema": schema, "name": table, "type": table_type, "columns": columns}


def _sanitize_server_and_port(server: str, port: int) -> tuple[str, int]:
    s = (server or "").strip()
    # Common prefixes from connection strings
    if s.lower().startswith("tcp:"):
        s = s[4:].strip()
    # Remove common trailing separators (frequently introduced when copying `Server=host,port;`)
    s = s.rstrip(" ,;")

    # Allow host,port in the server field (prefer explicit `port` if provided)
    if "," in s:
        host_part, port_part = s.rsplit(",", 1)
        host_part = host_part.strip().rstrip(" ,;")
        port_part = port_part.strip()
        if host_part and port_part.isdigit():
            maybe_port = int(port_part)
            if port <= 0 or port == 1433:
                port = maybe_port
            s = host_part

    # Allow host:port if port is default/unspecified (ignore IPv6 for now)
    if ":" in s and s.count(":") == 1:
        host_part, port_part = s.split(":", 1)
        host_part = host_part.strip().rstrip(" ,;")
        port_part = port_part.strip()
        if host_part and port_part.isdigit():
            maybe_port = int(port_part)
            if port <= 0 or port == 1433:
                port = maybe_port
            s = host_part

    s = s.strip().rstrip(" ,;")
    if not s:
        raise Datam8ValidationError(message="Missing server.", details=None)
    if port <= 0:
        raise Datam8ValidationError(message="Invalid port.", details={"port": port})
    return s, port


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def create_sqlserver_connector(config: dict[str, Any], runtime_secrets: dict[str, str]):
    mode = config.get("mode")
    if mode != "sql-user":
        raise Datam8ValidationError(message="Unsupported SQL Server mode.", details={"mode": mode})
    server = config.get("server")
    database = config.get("database")
    user = config.get("user")
    port = int(config.get("port") or 1433)
    encrypt = _truthy(config.get("encrypt", True))
    trust = _truthy(config.get("trustServerCertificate", True))
    password = runtime_secrets.get("password")
    if not isinstance(server, str) or not server.strip():
        raise Datam8ValidationError(message="Missing server.", details=None)
    if not isinstance(database, str) or not database.strip():
        raise Datam8ValidationError(message="Missing database.", details=None)
    if not isinstance(user, str) or not user.strip():
        raise Datam8ValidationError(message="Missing user.", details=None)
    if not password:
        raise Datam8PermissionError(code="auth", message="Missing required secret 'password'.", details=None)
    server_s, port_s = _sanitize_server_and_port(server, port)
    return SqlServerMetadataConnector(
        server=server_s,
        port=port_s,
        database=database,
        user=user,
        password=password,
        encrypt=encrypt,
        trust_server_certificate=trust,
    )
