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


class ApiModelStub:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_base_path_for_entity_type(self, _entity_type) -> Path:
        return self.root

    def get_entity_by_locator(self, _locator):
        return object()


def test_function_source_http_lifecycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(factory, "get_model", lambda: ApiModelStub(tmp_path / "Model"))
    client = TestClient(create_app())
    locator = "modelEntities/core/Customer"

    response = client.post(
        "/model/function/source",
        json={
            "locator": locator,
            "source": "helpers/normalize.sql",
            "content": "select 1",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    response = client.get(
        "/model/function/source",
        params={"locator": locator, "source": "helpers/normalize.sql"},
    )
    assert response.status_code == 200
    assert response.json() == {"content": "select 1"}

    response = client.post(
        "/model/function/rename",
        json={
            "locator": locator,
            "fromSource": "helpers/normalize.sql",
            "toSource": "normalize.sql",
        },
    )
    assert response.status_code == 200

    response = client.delete(
        "/model/function/source",
        params={"locator": locator, "source": "normalize.sql"},
    )
    assert response.status_code == 200

    response = client.post(
        "/model/function/source",
        json={"locator": locator, "source": "../outside.sql", "content": "unsafe"},
    )
    assert response.status_code == 400


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
