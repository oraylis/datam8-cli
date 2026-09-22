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

from datam8 import factory
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
            t.function is not None
            and (w.source_file.parent / Path(t.function.source)).is_file()
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
    create_server(host="127.0.0.1", port=8123, app=app)

    with TestClient(app):
        pass

    readiness = json.loads(capsys.readouterr().out)
    assert readiness == {
        "type": "ready",
        "baseUrl": "http://127.0.0.1:8123",
        "version": "2.0.0-test",
    }
