import asyncio
import gc
import sys
import weakref

import httpx
import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory, solution
from datam8.api.app import create_app
from datam8.secrets import SecretResolver
from datam8_model.plugin import PluginManifest


@pytest.fixture
def workspaces(tmp_path, monkeypatch):
    a, b = tmp_path / "a" / "A.dm8s", tmp_path / "b" / "B.dm8s"
    for path in (a, b):
        solution.init_solution(path)
    monkeypatch.setattr(config, "solution_path", a)
    monkeypatch.setattr(config, "solution_folder_path", a.parent)
    monkeypatch.setattr(factory, "_model", None)
    monkeypatch.setattr(factory, "_plugin_manager", None)
    factory.create_model()
    return a, b


def test_switch_preserves_failed_workspace_and_rejects_stale_writes(workspaces):
    a, b = workspaces
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        client.headers["Authorization"] = "Bearer test"
        first = client.get("/workspace").json()
        client.headers["X-DataM8-Workspace"] = first["workspaceId"]
        assert client.post("/workspace/open", json={"path": str(a)}).json() == first
        assert (
            client.post(
                "/workspace/open", json={"path": str(a.parent / "missing.dm8s")}
            ).status_code
            == 404
        )
        bad = b.parent / "Broken.dm8s"
        bad.write_text("{broken", encoding="utf-8")
        assert client.post("/workspace/open", json={"path": str(bad)}).status_code >= 400
        assert client.get("/workspace").json() == first
        assert factory.get_model().solution is not None
        second = client.post("/workspace/open", json={"path": str(b)}).json()
        assert second["path"] == str(b)
        assert second["workspaceId"] != first["workspaceId"]
        assert client.post("/model/save").status_code == 409
        client.headers["X-DataM8-Workspace"] = second["workspaceId"]
        assert client.get("/config").json()["name"] == "B"
        assert client.post("/model/save").status_code == 204
        assert client.post("/workspace/open", json={"path": str(a)}).status_code == 200


def test_switch_requires_opt_in_auth_and_current_workspace(workspaces):
    _, b = workspaces
    with TestClient(create_app()) as client:
        assert client.post("/workspace/open", json={"path": str(b)}).status_code == 403
    with pytest.raises(ValueError, match="token"):
        create_app(workspace_switch=True)
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        assert client.get("/workspace").status_code == 401
        assert (
            client.post(
                "/workspace/open", json={"path": str(b)}, headers={"Authorization": "Bearer test"}
            ).status_code
            == 409
        )


def test_unsaved_changes_block_switch(workspaces):
    _, b = workspaces
    # Use an entity tracked by the repository dirty-state mechanism.
    wrapper = next(factory.get_model().get_entity_iterator())
    wrapper.update(name=f"{wrapper.entity.name} changed")
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        client.headers["Authorization"] = "Bearer test"
        client.headers["X-DataM8-Workspace"] = client.get("/workspace").json()["workspaceId"]
        assert client.post("/workspace/open", json={"path": str(b)}).status_code == 409


def test_switch_waits_for_in_flight_request_and_its_response(workspaces):
    asyncio.run(check_concurrent_switch(workspaces))


async def check_concurrent_switch(workspaces):
    _, b = workspaces
    app = create_app(token="test", workspace_switch=True)
    entered, finish = asyncio.Event(), asyncio.Event()

    @app.get("/slow")
    async def slow():
        entered.set()
        await finish.wait()
        return {"name": config.get_name()}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test"},
    ) as client:
        client.headers["X-DataM8-Workspace"] = (await client.get("/workspace")).json()[
            "workspaceId"
        ]
        slow_task = asyncio.create_task(client.get("/slow"))
        await entered.wait()
        switch_task = asyncio.create_task(client.post("/workspace/open", json={"path": str(b)}))
        await asyncio.sleep(0.02)
        assert not switch_task.done()
        finish.set()
        assert (await slow_task).json() == {"name": "A"}
        assert (await switch_task).status_code == 200


def test_plugin_modules_manifests_and_secret_scope_reset(workspaces, monkeypatch):
    a, b = workspaces
    monkeypatch.setattr("datam8.secrets.keyring.get_keyring", lambda: None)
    monkeypatch.setattr(SecretResolver, "_SecretResolver__instance", None)
    for path, marker in ((a, "A"), (b, "B")):
        directory = path.parent / factory.get_model().solution.pluginsPath
        directory.mkdir(exist_ok=True)
        (directory / "connector.py").write_text(
            f"class Marker:\n    value = '{marker}'\n", encoding="utf-8"
        )
        manifest = PluginManifest(
            id="local",
            displayName="Local",
            version="1",
            entryPoint="connector.py:Marker",
            capabilities=[],
        )
        (directory / "plugin.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    # Both solutions deliberately use the same module and plugin IDs.
    factory.get_plugin_manager(reset=True)
    original_resolver = SecretResolver()
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        client.headers["Authorization"] = "Bearer test"
        for path, marker in ((a, "A"), (b, "B"), (a, "A"), (b, "B")):
            client.headers["X-DataM8-Workspace"] = client.get("/workspace").json()["workspaceId"]
            assert client.post("/workspace/open", json={"path": str(path)}).status_code == 200
            assert factory.get_plugin_manager().get_plugin("local").value == marker
        assert SecretResolver() is not original_resolver
        assert SecretResolver()._SecretResolver__service_name == "datam8:B"
        assert sys.modules["connector"].__file__.startswith(str(b.parent))
    sys.modules.pop("connector", None)


def test_bad_plugin_manifest_rolls_back_loaded_model(workspaces):
    a, b = workspaces
    plugins_dir = b.parent / factory.get_model().solution.pluginsPath
    plugins_dir.mkdir(exist_ok=True)
    (plugins_dir / "bad.json").write_text("{}", encoding="utf-8")
    previous = factory.get_model()
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        client.headers["Authorization"] = "Bearer test"
        original = client.get("/workspace").json()
        client.headers["X-DataM8-Workspace"] = original["workspaceId"]
        assert client.post("/workspace/open", json={"path": str(b)}).status_code == 400
        assert client.get("/workspace").json() == original
        assert factory.get_model() is previous
        assert config.solution_path == a


def test_repeated_switches_release_old_models(workspaces):
    a, b = workspaces
    old_models = []
    with TestClient(create_app(token="test", workspace_switch=True)) as client:
        client.headers["Authorization"] = "Bearer test"
        for path in [b, a] * 8:
            old_models.append(weakref.ref(factory.get_model()))
            client.headers["X-DataM8-Workspace"] = client.get("/workspace").json()["workspaceId"]
            assert client.post("/workspace/open", json={"path": str(path)}).status_code == 200
    gc.collect()
    assert all(reference() is None for reference in old_models)
