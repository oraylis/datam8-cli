from __future__ import annotations

from datam8.core.connectors.registry import ConnectorSource, connector_registry
from datam8.core.connectors.http_api import create_http_api_connector
from datam8.core.connectors.oracle import create_oracle_connector
from datam8.core.connectors.sqlserver import create_sqlserver_connector
from datam8.core.connectors.types import ConnectorModule


SQLSERVER_MANIFEST = {
    "name": "sqlserver",
    "version": "0.1.0",
    "description": "Microsoft SQL Server metadata connector",
    "aliases": [
        "sqlserver",
        "SqlDataSource",
        "SqlServerDataSource",
        "sql",
        "sqldatasource",
        "sqlserverdatasource",
        "mssql",
    ],
    "connectionSchema": {
        "fields": [
            {
                "path": "mode",
                "label": "Mode",
                "type": "string",
                "required": True,
                "options": [{"value": "sql-user", "label": "Host / DB / User"}],
            },
            {"path": "encrypt", "label": "Encrypt", "type": "boolean"},
            {"path": "trustServerCertificate", "label": "Trust server certificate", "type": "boolean"},
        ],
        "variants": {
            "discriminatorPath": "mode",
            "variants": [
                {
                    "discriminatorValue": "sql-user",
                    "fields": [
                        {"path": "server", "label": "Server", "type": "string", "required": True},
                        {"path": "port", "label": "Port", "type": "number"},
                        {"path": "database", "label": "Database", "type": "string", "required": True},
                        {"path": "user", "label": "User", "type": "string", "required": True},
                    ],
                }
            ],
        },
    },
    "requiredSecrets": ["password"],
}


HTTP_API_MANIFEST = {
    "name": "http-api",
    "version": "0.1.0",
    "description": "HTTP API connector (REST JSON)",
    "aliases": [
        "http-api",
        "HttpApiDataSource",
        "PowerBiDataSource",
        "http",
        "httpapi",
        "HttpApiRestConnector",
        "HttpApiConnector",
    ],
    "connectionSchema": {
        "fields": [
            {"path": "baseUrl", "label": "Base URL", "type": "string", "required": True},
            {"path": "responseArrayPath", "label": "Response array path", "type": "string"},
            {"path": "requestTimeoutMs", "label": "Request timeout (ms)", "type": "number"},
            {"path": "tokenRequestTimeoutMs", "label": "Token timeout (ms)", "type": "number"},
            {
                "path": "auth.kind",
                "label": "Auth kind",
                "type": "string",
                "required": True,
                "options": [
                    {"value": "none", "label": "None"},
                    {"value": "api-key-header", "label": "API Key (header)"},
                    {"value": "basic", "label": "Basic"},
                    {"value": "bearer-static", "label": "Bearer token"},
                    {"value": "oauth2-client-credentials", "label": "OAuth2 client credentials"},
                ],
            },
        ],
        "variants": {
            "discriminatorPath": "auth.kind",
            "variants": [
                {"discriminatorValue": "none", "fields": []},
                {
                    "discriminatorValue": "api-key-header",
                    "fields": [{"path": "auth.headerName", "label": "Header name", "type": "string", "required": True}],
                },
                {"discriminatorValue": "basic", "fields": [{"path": "auth.username", "label": "Username", "type": "string", "required": True}]},
                {"discriminatorValue": "bearer-static", "fields": []},
                {
                    "discriminatorValue": "oauth2-client-credentials",
                    "fields": [
                        {"path": "auth.tokenUrl", "label": "Token URL", "type": "string", "required": True},
                        {"path": "auth.clientId", "label": "Client ID", "type": "string", "required": True},
                        {"path": "auth.scope", "label": "Scope", "type": "string"},
                        {"path": "auth.tenantId", "label": "Tenant ID", "type": "string"},
                    ],
                },
            ],
        },
    },
    "requiredSecrets": {
        "discriminatorPath": "auth.kind",
        "variants": {
            "none": [],
            "api-key-header": ["apiKey"],
            "basic": ["password"],
            "bearer-static": ["token"],
            "oauth2-client-credentials": ["clientSecret"],
        },
    },
}

ORACLE_MANIFEST = {
    "name": "oracle",
    "version": "0.1.0",
    "description": "Oracle metadata connector",
    "aliases": ["OracleDataSource", "oracle", "oracledatasource"],
    "connectionSchema": {
        "fields": [
            {
                "path": "mode",
                "label": "Mode",
                "type": "string",
                "required": True,
                "options": [{"value": "host-service", "label": "Host / Port / Service name"}],
            },
            {"path": "user", "label": "User", "type": "string", "required": True},
        ],
        "variants": {
            "discriminatorPath": "mode",
            "variants": [
                {
                    "discriminatorValue": "host-service",
                    "fields": [
                        {"path": "host", "label": "Host", "type": "string", "required": True},
                        {"path": "port", "label": "Port", "type": "number"},
                        {"path": "serviceName", "label": "Service name", "type": "string", "required": True},
                    ],
                }
            ],
        },
    },
    "requiredSecrets": ["password"],
}

def register_builtin_connectors() -> None:
    connector_registry.register(
        ConnectorModule(manifest=SQLSERVER_MANIFEST, create_connector=create_sqlserver_connector),
        ConnectorSource(kind="builtin"),
    )
    connector_registry.register(
        ConnectorModule(manifest=HTTP_API_MANIFEST, create_connector=create_http_api_connector),
        ConnectorSource(kind="builtin"),
    )
    connector_registry.register(
        ConnectorModule(manifest=ORACLE_MANIFEST, create_connector=create_oracle_connector),
        ConnectorSource(kind="builtin"),
    )
