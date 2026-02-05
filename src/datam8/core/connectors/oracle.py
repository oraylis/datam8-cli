from __future__ import annotations

from typing import Any

from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8PermissionError,
    Datam8ValidationError,
)


class OracleMetadataConnector:
    def __init__(
        self,
        *,
        user: str,
        password: str,
        host: str,
        port: int,
        service_name: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds

    def _connect(self):
        try:
            try:
                import oracledb  # type: ignore
            except Exception as e:
                raise Datam8ExternalSystemError(
                    code="missing_dependency",
                    message="Oracle connector dependency is missing (oracledb).",
                    details={"error": str(e)},
                    hint="Install dependencies and restart: pip install oracledb",
                )
            dsn = oracledb.makedsn(self.host, self.port, service_name=self.service_name)
            return oracledb.connect(user=self.user, password=self.password, dsn=dsn)
        except Exception as e:
            if isinstance(e, (Datam8ExternalSystemError, Datam8PermissionError, Datam8ValidationError)):
                raise
            msg = str(e).lower()
            if "ora-01017" in msg or "invalid username/password" in msg:
                raise Datam8PermissionError(code="auth", message="Authentication failed.", details={"error": str(e)})
            raise Datam8ExternalSystemError(code="oracle_error", message="Oracle connection failed.", details={"error": str(e)})

    def test_connection(self) -> dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM DUAL")
            _ = cur.fetchone()
        return {"ok": True}

    def list_schemas(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT USERNAME FROM ALL_USERS ORDER BY USERNAME")
            rows = cur.fetchall() or []
            return [{"name": r[0]} for r in rows]

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        schema = (schema or "").strip().upper() or None
        query = """
            SELECT OWNER AS SCHEMA, TABLE_NAME AS NAME, 'BASE TABLE' AS TYPE
            FROM ALL_TABLES
            {where_tables}
            UNION ALL
            SELECT OWNER AS SCHEMA, VIEW_NAME AS NAME, 'VIEW' AS TYPE
            FROM ALL_VIEWS
            {where_views}
            ORDER BY 1, 2
        """
        where = "WHERE OWNER = :schema" if schema else ""
        sql = query.format(where_tables=where, where_views=where)
        binds = {"schema": schema} if schema else {}

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, binds)
            rows = cur.fetchall() or []
            return [{"schema": r[0], "name": r[1], "type": r[2]} for r in rows]

    def get_table_metadata(self, *, schema: str, table: str) -> dict[str, Any]:
        schema_u = (schema or "").strip().upper()
        table_u = (table or "").strip().upper()
        if not schema_u:
            raise Datam8ValidationError(message="schema is required", details=None)
        if not table_u:
            raise Datam8ValidationError(message="table is required", details=None)

        with self._connect() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT OBJECT_TYPE
                FROM ALL_OBJECTS
                WHERE OWNER = :p_schema
                  AND OBJECT_NAME = :p_table
                  AND OBJECT_TYPE IN ('TABLE','VIEW')
                """,
                {"p_schema": schema_u, "p_table": table_u},
            )
            row = cur.fetchone()
            if not row:
                raise Datam8ValidationError(message="Table or view not found.", details={"schema": schema_u, "table": table_u})

            object_type = row[0]
            table_type = "VIEW" if object_type == "VIEW" else "BASE TABLE"

            cur.execute(
                """
                SELECT COLUMN_NAME, COLUMN_ID, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :p_schema
                  AND TABLE_NAME = :p_table
                ORDER BY COLUMN_ID
                """,
                {"p_schema": schema_u, "p_table": table_u},
            )
            col_rows = cur.fetchall() or []

            cur.execute(
                """
                SELECT acc.COLUMN_NAME
                FROM ALL_CONSTRAINTS ac
                JOIN ALL_CONS_COLUMNS acc
                  ON ac.OWNER = acc.OWNER
                 AND ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
                WHERE ac.OWNER = :p_schema
                  AND ac.TABLE_NAME = :p_table
                  AND ac.CONSTRAINT_TYPE = 'P'
                """,
                {"p_schema": schema_u, "p_table": table_u},
            )
            pk_cols = {r[0] for r in (cur.fetchall() or [])}

            columns = []
            for r in col_rows:
                name = r[0]
                columns.append(
                    {
                        "name": name,
                        "ordinal": int(r[1]) if r[1] is not None else None,
                        "dataType": r[2],
                        "maxLength": int(r[3]) if r[3] is not None else None,
                        "numericPrecision": int(r[4]) if r[4] is not None else None,
                        "numericScale": int(r[5]) if r[5] is not None else None,
                        "isNullable": str(r[6]).upper() == "Y",
                        "isPrimaryKey": name in pk_cols,
                    }
                )

            return {"schema": schema_u, "name": table_u, "type": table_type, "columns": columns}


def create_oracle_connector(config: dict[str, Any], runtime_secrets: dict[str, str]):
    mode = config.get("mode")
    if mode != "host-service":
        raise Datam8ValidationError(message="Unsupported Oracle mode.", details={"mode": mode})
    host = config.get("host")
    service_name = config.get("serviceName")
    user = config.get("user")
    port = int(config.get("port") or 1521)
    password = runtime_secrets.get("password")

    if not isinstance(host, str) or not host.strip():
        raise Datam8ValidationError(message="Missing Oracle host.", details=None)
    if not isinstance(service_name, str) or not service_name.strip():
        raise Datam8ValidationError(message="Missing Oracle serviceName.", details=None)
    if not isinstance(user, str) or not user.strip():
        raise Datam8ValidationError(message="Missing Oracle user.", details=None)
    if not password:
        raise Datam8PermissionError(code="auth", message="Missing required secret 'password'.", details=None)

    return OracleMetadataConnector(
        user=user.strip(),
        password=password,
        host=host.strip(),
        port=port,
        service_name=service_name.strip(),
    )
