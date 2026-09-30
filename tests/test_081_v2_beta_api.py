# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import json
from pathlib import Path

from fastapi.testclient import TestClient

from datam8 import factory, source
from datam8.api.app import create_app, create_server
from datam8.model import Model


def test_function_http_lifecycle(
    model: Model,
    monkeypatch,
) -> None:
    monkeypatch.setattr(factory, "get_model", lambda: model)
    client = TestClient(create_app())

    # Find a model entity with a function whose source exists in the solution.
    # The sample solution contains shared/nested function layouts, so do not
    # depend on repository iteration order here.
    wrapper = next(
        w
        for w in model.modelEntities.values()
        if any(
            t.function is not None and (w.source_file.parent / Path(t.function.source)).is_file()
            for t in w.entity.transformations
        )
    )
    entity_id = wrapper.entity.id
    step_no = next(t.stepNo for t in wrapper.entity.transformations if t.function is not None)

    # GET function by step number
    response = client.get(f"/functions/{entity_id}/{step_no}")
    assert response.status_code == 200
    data = response.json()
    assert "item" in data
    assert "sourceCode" in data["item"] or "source_code" in data["item"]

    # GET all functions for entity
    response = client.get(f"/functions/{entity_id}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_server_readiness_uses_json_contract(capsys, monkeypatch) -> None:
    monkeypatch.setattr("datam8.api.app.config.get_version", lambda: "2.0.0-test")
    app = create_app()
    server = create_server(host="127.0.0.1", port=8123, app=app)

    with TestClient(server.config.app):
        pass

    readiness = json.loads(capsys.readouterr().out)
    assert readiness == {
        "type": "ready",
        "baseUrl": "http://127.0.0.1:8123",
        "version": "2.0.0-test",
    }


def test_unexpected_error_response_includes_cors_headers(monkeypatch) -> None:
    monkeypatch.delenv("DATAM8_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DATAM8_CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.setattr(factory, "get_model", lambda: object())

    def fail_compare(*args, **kwargs):
        raise ValueError("No target data type mapping found for 'datetime'")

    monkeypatch.setattr(source, "compare_entity_with_source", fail_compare)
    server = create_server(host="127.0.0.1", port=8123, app=create_app())

    with TestClient(server.config.app, raise_server_exceptions=False) as client:
        response = client.get(
            "/sources/compare?locator=modelEntities%2Ftest",
            headers={"Origin": "http://localhost:4320"},
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:4320"
    assert response.json()["message"] == (
        "Unexpected error - No target data type mapping found for 'datetime'"
    )


def test_cors_preflight_and_disallowed_origin(monkeypatch) -> None:
    monkeypatch.delenv("DATAM8_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("DATAM8_CORS_ORIGIN_REGEX", raising=False)
    server = create_server(host="127.0.0.1", port=8123, app=create_app(token="test-token"))

    with TestClient(server.config.app) as client:
        preflight = client.options(
            "/sources/compare",
            headers={
                "Origin": "http://localhost:4320",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        disallowed = client.get(
            "/health",
            headers={"Origin": "https://not-allowed.example"},
        )
        unauthorized = client.get(
            "/sources/compare?locator=modelEntities/test",
            headers={"Origin": "http://localhost:4320"},
        )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:4320"
    assert disallowed.status_code == 204
    assert "access-control-allow-origin" not in disallowed.headers
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == "http://localhost:4320"
