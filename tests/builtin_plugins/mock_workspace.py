"""Local HTTP fixture; never contacts a Databricks workspace."""

from __future__ import annotations

import base64
import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


class MockWorkspace:
    def __init__(self):
        self.requests = []
        self.error = None
        self.repeat_page = False
        self.preview_state = "SUCCEEDED"
        self.chunked = False
        self.empty_preview = False
        self.columns = [
            {
                "name": "id",
                "type_name": "LONG",
                "type_text": "bigint",
                "position": 0,
                "nullable": False,
                "comment": "Customer key",
            },
            {
                "name": "name",
                "type_name": "STRING",
                "type_text": "varchar(80)",
                "position": 1,
                "nullable": True,
            },
            {
                "name": "amount",
                "type_name": "DECIMAL",
                "type_text": "decimal(10,0)",
                "position": 2,
                "type_precision": 10,
                "type_scale": 0,
                "nullable": True,
            },
            {
                "name": "active",
                "type_name": "BOOLEAN",
                "type_text": "boolean",
                "position": 3,
                "nullable": True,
            },
            {
                "name": "details",
                "type_name": "STRUCT",
                "type_text": "struct<city:string>",
                "position": 4,
                "nullable": True,
            },
        ]
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                parsed = urlsplit(self.path)
                query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                request = {
                    "method": self.command,
                    "path": unquote(parsed.path),
                    "query": query,
                    "body": body.decode(),
                    "authorization": self.headers.get("Authorization"),
                }
                owner.requests.append(request)
                status, payload = owner.dispatch(request)
                encoded = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if status == 302:
                    self.send_header("Location", owner.url + "/redirect-target")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def dispatch(self, request):
        path, query = request["path"], request["query"]
        if self.error:
            return self.error, {"message": "developer-pat client-secret NEVER-ECHO-THIS"}
        if path.endswith("/token"):
            form = parse_qs(request["body"])
            if path == "/oidc/v1/token":
                expected = "Basic " + base64.b64encode(b"client-id:client-secret").decode()
                assert request["authorization"] == expected
                assert form == {
                    "grant_type": ["client_credentials"],
                    "scope": ["all-apis"],
                }
            else:
                assert form["client_id"] == ["client-id"]
                assert form["client_secret"] == ["client-secret"]
                assert form["scope"] == ["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"]
            return 200, {"access_token": "oauth-token", "expires_in": 3600}
        if request["authorization"] not in {
            "Bearer developer-pat",
            "Bearer oauth-token",
        }:
            return 401, {"error_code": "UNAUTHENTICATED"}
        token = query.get("page_token")
        if self.repeat_page:
            return 200, {path.rsplit("/", 1)[1]: [], "next_page_token": "repeat"}
        if path.endswith("/catalogs"):
            return 200, {"catalogs": [{"name": "main"}]} if token else {
                "catalogs": [],
                "next_page_token": "next",
            }
        if path.endswith("/schemas"):
            assert query["catalog_name"] == "main"
            return 200, {"schemas": [{"name": "sales"}, {"name": "empty"}]} if token else {
                "schemas": [],
                "next_page_token": "next",
            }
        if path.endswith("/tables"):
            assert query["catalog_name"] == "main"
            if query["schema_name"] == "empty":
                return 200, {"tables": []}
            return 200, {
                "tables": [
                    {
                        "name": "Customers",
                        "table_type": "MANAGED",
                        "comment": "CRM customers",
                    },
                    {"name": "CustomerView", "table_type": "VIEW"},
                ]
            } if token else {"tables": [], "next_page_token": "next"}
        if "/unity-catalog/tables/" in path:
            return 200, {
                "name": "Customers",
                "table_type": "MANAGED",
                "comment": "CRM customers",
                "columns": copy.deepcopy(self.columns),
                "table_constraints": [
                    {"primary_key_constraint": {"name": "pk", "child_columns": ["id"]}}
                ],
            }
        if path.endswith("/cancel"):
            return 200, {}
        if "/result/chunks/" in path:
            return 200, {"data_array": [["2", None]], "chunk_index": 1}
        if path == "/api/2.0/sql/statements":
            data = json.loads(request["body"])
            assert data["warehouse_id"] == "warehouse1"
            assert 5 <= int(data["wait_timeout"][:-1]) <= 30
            assert data["on_wait_timeout"] == "CANCEL"
            result = {"data_array": [] if self.empty_preview else [["1", "Alice"], ["2", None]]}
            if self.chunked:
                result = {"data_array": [["1", "Alice"]], "next_chunk_index": 1}
            return 200, {
                "statement_id": "statement1",
                "status": {
                    "state": self.preview_state,
                    "error": {"message": "NEVER-ECHO-THIS client-secret"},
                },
                "manifest": {"schema": {"columns": [{"name": "id"}, {"name": "name"}]}},
                "result": result,
            }
        return 404, {}
