from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory, generate
from datam8.api.app import create_app
from datam8.api.routes import secrets as secret_routes
from datam8.model import Model
from datam8.plugins.base import TableMetadata
from datam8_model.data_source import SourceObject
from datam8_model.plugin import Capability


@pytest.fixture
def isolated_api_model(tmp_path: Path) -> Iterator[tuple[Model, Path]]:
    source_solution = Path(os.environ["DATAM8_SOLUTION_PATH"]).resolve()
    solution_root = tmp_path / "sample-solution"
    shutil.copytree(
        source_solution.parent,
        solution_root,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".databricks",
            ".pytest_cache",
            "Output",
            "__pycache__",
        ),
    )
    solution_path = solution_root / source_solution.name

    config.set_solution(solution_path)
    config.lazy = False
    factory._model = None
    factory._plugin_manager = None
    datam8_model = factory.create_model(solution_path)
    datam8_model.resolve()

    yield datam8_model, solution_path

    generate.payload_functions.clear()
    factory._model = None
    factory._plugin_manager = None


class SourcePluginStub:
    def test_connection(self):
        return None

    def list_source(self, source_location: str | None):
        if source_location is None:
            return pl.DataFrame(
                [
                    {"schema": "dbo", "name": "Customer", "type": "TABLE"},
                    {"schema": "sales", "name": "Order", "type": "TABLE"},
                ]
            )
        return pl.DataFrame(
            [
                {
                    "schema": source_location,
                    "name": "Customer",
                    "type": "TABLE",
                    "description": "Customer source",
                }
            ]
        )

    def get_table_metadata(self, source_location: str) -> TableMetadata:
        schema, _, name = source_location.rpartition(".")
        return TableMetadata(
            pl.DataFrame(
                [
                    {
                        "name": "CustomerId",
                        "ordinal": 1,
                        "dataType": "int",
                        "isNullable": False,
                        "isPrimaryKey": True,
                    }
                ]
            ),
            SourceObject(
                schema=schema or None,
                name=name or source_location,
                type="TABLE",
                description="Customer source",
            ),
        )

    def preview_data(self, source_location: str, *, limit: int):
        return pl.DataFrame(
            [{"sourceLocation": source_location, "rowNumber": 1}]
        ).lazy().limit(limit)

    def is_capable_of(self, capability: Capability) -> bool:
        return capability == Capability.PREVIEW_DATA

    def resolve_source_type(self, source_type: str) -> str:
        assert source_type == "int"
        return "int"


class SecretResolverStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    @staticmethod
    def normalize(path: str) -> str:
        return path.removeprefix("ref://")

    def get_secret(self, path: str) -> str | None:
        return self.values.get(self.normalize(path))

    def set_secret(self, path: str, value: str, *, force: bool = False) -> None:
        normalized = self.normalize(path)
        if normalized in self.values and not force:
            raise ValueError("Secret already exists")
        self.values[normalized] = value


def test_all_api_endpoints_with_sample_solution(
    isolated_api_model: tuple[Model, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datam8_model, solution_path = isolated_api_model
    token = "sample-api-final-test"
    app = create_app(token=token, enable_openapi=True)
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {token}"},
        raise_server_exceptions=False,
    )
    unauthenticated_client = TestClient(app, raise_server_exceptions=False)
    covered: set[tuple[str, str]] = set()

    def request(
        method: str,
        route: str,
        concrete_path: str | None = None,
        *,
        expected: int = 200,
        **kwargs,
    ):
        response = client.request(method, concrete_path or route, **kwargs)
        assert response.status_code == expected, (
            f"{method} {concrete_path or route}: "
            f"{response.status_code} {response.text}"
        )
        if expected < 400:
            covered.add((method, route))
        return response

    # System, auth, CORS, and solution reads.
    assert unauthenticated_client.get("/health").status_code == 200
    assert unauthenticated_client.get("/version").status_code == 200
    assert unauthenticated_client.get("/config").status_code == 401
    assert (
        client.options(
            "/config",
            headers={
                "Origin": "http://localhost:4321",
                "Access-Control-Request-Method": "GET",
            },
        ).status_code
        == 200
    )
    request("GET", "/health")
    request("GET", "/version")
    assert Path(request("GET", "/config").json()["solutionFilePath"]) == solution_path
    request("GET", "/solution")
    full_solution = request("GET", "/solution/full").json()
    assert full_solution["model_entities"]
    assert full_solution["folder_entities"]
    assert full_solution["base_entities"]
    entity_list = request(
        "GET",
        "/entities/{locator:path}",
        "/entities/modelEntities/020-Core/Sales/Customer/",
    ).json()
    assert entity_list["count"] > 0

    # Plugin API uses the real built-in manifests and classes.
    request("GET", "/plugins/")
    request("POST", "/plugins/reload")
    request("GET", "/plugins/{plugin_id}", "/plugins/builtin:SQLServer")
    request(
        "GET",
        "/plugins/{plugin_id}/ui-schema",
        "/plugins/builtin:SQLServer/ui-schema",
    )
    request(
        "GET",
        "/plugins/{plugin_id}/data-type-mappings",
        "/plugins/builtin:SQLServer/data-type-mappings",
    )
    request(
        "GET",
        "/plugins/{plugin_id}/connection-properties",
        "/plugins/builtin:SQLServer/connection-properties",
    )

    # Secrets are tested without writing to the developer's operating-system keyring.
    secret_resolver = SecretResolverStub()
    monkeypatch.setattr(secret_routes, "SecretResolver", lambda: secret_resolver)
    request(
        "POST",
        "/secrets/check",
        json={"path": "ref://api/password"},
        expected=404,
    )
    request(
        "PUT",
        "/secrets/set",
        json={"path": "ref://api/password", "value": "first"},
        expected=204,
    )
    request(
        "PUT",
        "/secrets/set",
        json={"path": "api/password", "value": "updated"},
        expected=204,
    )
    request("POST", "/secrets/check", json={"path": "ref://api/password"})
    covered.add(("PUT", "/secrets/set"))

    # Reload conflict and force semantics.
    request(
        "PATCH",
        "/entities/{locator:path}",
        "/entities/dataTypes/string",
        json={"description": "API test pending change"},
    )
    request("GET", "/model/unsaved")
    request("POST", "/model/reload", expected=409)
    request("POST", "/model/reload", "/model/reload?force=true")
    datam8_model = factory.get_model()

    # Base-entity create, patch, clone, rename, delete, save, and reload.
    data_type_payload = datam8_model.dataTypes.get("string").entity.to_dict()
    data_type_payload.pop("name", None)
    request(
        "PUT",
        "/entities/{locator:path}",
        "/entities/dataTypes/ApiText",
        json=data_type_payload,
    )
    request(
        "PATCH",
        "/entities/{locator:path}",
        "/entities/dataTypes/ApiText",
        json={"displayName": "API Text"},
    )
    request(
        "PUT",
        "/entities/clone",
        json={
            "locator": "dataTypes/ApiText",
            "newLocator": "dataTypes/ApiTextClone",
        },
    )
    request(
        "POST",
        "/entities/rename",
        json={"from": "dataTypes/ApiText", "to": "dataTypes/ApiTextRenamed"},
    )
    request(
        "DELETE",
        "/entities/{locator:path}",
        "/entities/dataTypes/ApiTextClone",
    )
    request("POST", "/model/save", json={})
    request("POST", "/model/reload")
    assert factory.get_model().has_locator("dataTypes/ApiTextRenamed")
    assert not factory.get_model().has_locator("dataTypes/ApiTextClone")

    # Function source lifecycle on an actual sample model entity.
    function_locator = "modelEntities/020-Core/Sales/Customer/Customer"
    request(
        "POST",
        "/model/function/source",
        json={
            "locator": function_locator,
            "source": "api/helpers.py",
            "content": "def api_test():\n    return True\n",
        },
    )
    function_read = request(
        "GET",
        "/model/function/source",
        params={"locator": function_locator, "source": "api/helpers.py"},
    )
    assert "api_test" in function_read.json()["content"]
    request(
        "POST",
        "/model/function/rename",
        json={
            "locator": function_locator,
            "fromSource": "api/helpers.py",
            "toSource": "api/renamed.py",
        },
    )
    request(
        "DELETE",
        "/model/function/source",
        params={"locator": function_locator, "source": "api/renamed.py"},
    )
    request(
        "POST",
        "/model/function/source",
        json={"locator": function_locator, "source": "../escape.py", "content": "x"},
        expected=400,
    )

    # Recursive folder move/delete, including a nested model and function tree.
    folder_payload = datam8_model.folders.get(
        "folders/020-Core/Sales/Customer"
    ).entity.to_dict()
    folder_payload["id"] = 999001
    folder_payload.pop("name", None)
    folder_payload.pop("path", None)
    request(
        "PUT",
        "/entities/{locator:path}",
        "/entities/folders/020-Core/ApiTree",
        json=folder_payload,
    )
    request(
        "PUT",
        "/entities/clone",
        json={
            "locator": function_locator,
            "newLocator": "modelEntities/020-Core/ApiTree/ApiCustomer",
        },
    )
    request("POST", "/model/save", json={})
    request(
        "POST",
        "/model/function/source",
        json={
            "locator": "modelEntities/020-Core/ApiTree/ApiCustomer",
            "source": "transform.py",
            "content": "print('api')\n",
        },
    )
    moved = request(
        "POST",
        "/entities/move",
        json={
            "from": "folders/020-Core/ApiTree",
            "to": "folders/020-Core/ApiTreeMoved",
        },
    ).json()
    assert moved["count"] == 2
    request("POST", "/model/save", json={})
    moved_function = (
        solution_path.parent
        / "Model"
        / "020-Core"
        / "ApiTreeMoved"
        / "ApiCustomer"
        / "transform.py"
    )
    assert moved_function.is_file()
    deleted = request(
        "DELETE",
        "/entities/{locator:path}",
        "/entities/folders/020-Core/ApiTreeMoved",
    ).json()
    assert deleted["count"] == 2
    request("POST", "/model/save", json={})
    assert not moved_function.parent.exists()

    # Source routes use a deterministic plugin while retaining the real model/import code.
    source_plugin = SourcePluginStub()
    monkeypatch.setattr(
        factory,
        "get_plugin_for_data_source",
        lambda *_args, **_kwargs: source_plugin,
    )
    request("GET", "/sources/{data_source}/test", "/sources/AdventureWorks/test")
    request(
        "GET",
        "/sources/{data_source}/locations",
        "/sources/AdventureWorks/locations",
    )
    request(
        "GET",
        "/sources/{data_source}/locations/metadata",
        "/sources/AdventureWorks/locations/metadata?source_location=dbo.Customer",
    )
    request(
        "GET",
        "/sources/{data_source}/locations/preview",
        "/sources/AdventureWorks/locations/preview?source_location=dbo.Customer&limit=1",
    )
    request(
        "PUT",
        "/sources/{data_source}/import",
        "/sources/AdventureWorks/import",
        json={
            "locator": "modelEntities/010-Stage/ApiCanonical",
            "sourceLocation": "dbo.Customer",
        },
    )
    request(
        "GET",
        "/sources/{data_source}/schemas",
        "/sources/AdventureWorks/schemas",
    )
    request(
        "GET",
        "/sources/{data_source}/schemas/{schema}/tables",
        "/sources/AdventureWorks/schemas/dbo/tables",
    )
    request(
        "GET",
        "/sources/{data_source}/schemas/{schema}/tables/{table}",
        "/sources/AdventureWorks/schemas/dbo/tables/Customer",
    )
    request(
        "GET",
        "/sources/{data_source}/schemas/{schema}/tables/{table}/preview",
        "/sources/AdventureWorks/schemas/dbo/tables/Customer/preview?limit=1",
    )
    request(
        "PUT",
        "/sources/{data_source}/schemas/{schema}/tables/{table}/import",
        "/sources/AdventureWorks/schemas/dbo/tables/Customer/import",
        json={"locator": "modelEntities/010-Stage/ApiSchema"},
    )
    request(
        "GET",
        "/sources/{data_source}/tables",
        "/sources/AdventureWorks/tables",
    )
    request(
        "GET",
        "/sources/{data_source}/tables/{table}",
        "/sources/AdventureWorks/tables/Customer",
    )
    request(
        "GET",
        "/sources/{data_source}/tables/{table}/preview",
        "/sources/AdventureWorks/tables/Customer/preview?limit=1",
    )
    request(
        "PUT",
        "/sources/{data_source}/tables/{table}/import",
        "/sources/AdventureWorks/tables/Customer/import",
        json={"locator": "modelEntities/010-Stage/ApiTable"},
    )
    request(
        "GET",
        "/sources/compare",
        "/sources/compare?locator=modelEntities/010-Stage/ApiCanonical",
    )
    request(
        "GET",
        "/sources/{data_source}/usages",
        "/sources/AdventureWorks/usages",
    )

    # Real template loading and generation from the isolated sample solution.
    generated = request(
        "POST",
        "/model/generate",
        json={"target": "docs", "cleanOutput": True},
    ).json()
    assert Path(generated["outputPath"]).is_dir()

    registered = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
        and not route.path.startswith(("/openapi", "/docs", "/redoc"))
    }
    assert covered == registered, (
        f"Missing endpoint coverage: {sorted(registered - covered)}; "
        f"unknown coverage: {sorted(covered - registered)}"
    )
