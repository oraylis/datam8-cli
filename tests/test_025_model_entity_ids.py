"""ID allocation, validation and persistence using disposable solutions."""

import asyncio
import json
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from datam8 import config, factory, solution
from datam8.api.app import create_app
from datam8.app import app
from datam8.errors import Datam8ValidationError
from datam8.utils.ids import MAX_ENTITY_ID


def entity_data(name="Existing", entity_id=7):
    return {
        "id": entity_id,
        "name": name,
        "attributes": [
            {
                "name": "Id",
                "ordinalNumber": 1,
                "attributeType": "Regular",
                "dataType": {"type": "int", "nullable": False},
                "dateAdded": "2026-01-01T00:00:00Z",
            }
        ],
        "sources": [],
        "relationships": [],
        "transformations": [],
    }


@pytest.fixture
def id_workspace(tmp_path, monkeypatch):
    path = tmp_path / "IDs.dm8s"
    solution.init_solution(path)
    (tmp_path / "base/Zones.json").write_text(
        json.dumps(
            {"type": "zones", "zones": [{"name": "Raw", "targetName": "raw", "displayName": "Raw"}]}
        ),
        encoding="utf-8",
    )
    folder = tmp_path / "model/Raw"
    folder.mkdir(parents=True)
    (folder / ".properties.json").write_text(
        json.dumps({"type": "folders", "folders": [{"id": 11, "name": "Raw", "path": "Raw"}]}),
        encoding="utf-8",
    )
    (folder / "Existing.json").write_text(json.dumps(entity_data()), encoding="utf-8")
    monkeypatch.setattr(config, "solution_path", path, raising=False)
    monkeypatch.setattr(config, "solution_folder_path", tmp_path, raising=False)
    monkeypatch.setattr(config, "lazy", True)
    monkeypatch.setattr(config, "mode", config.RunMode.TEST)
    monkeypatch.setattr(factory, "_model", None)
    return path


def test_allocation_retries_loaded_and_reserved_ids(id_workspace, monkeypatch):
    model = factory.get_model()
    draws = iter([6, 10, MAX_ENTITY_ID - 1, MAX_ENTITY_ID - 1, 0])
    monkeypatch.setattr("datam8.utils.ids.secrets.randbelow", lambda _: next(draws))
    assert model.get_next_model_id() == MAX_ENTITY_ID
    assert model.get_next_model_id() == 1


def test_parallel_allocation_reserves_unique_safe_ids(id_workspace):
    model = factory.get_model()
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _: model.get_next_model_id(), range(500)))
    assert len(set(ids)) == 500
    assert 7 not in ids
    assert all(type(value) is int and 1 <= value <= MAX_ENTITY_ID for value in ids)


def test_create_clone_update_move_and_reload_keep_actual_ids(id_workspace, monkeypatch):
    factory.get_model()
    original_randbelow = secrets.randbelow
    draws = iter([MAX_ENTITY_ID - 1, 0])
    monkeypatch.setattr("datam8.utils.ids.secrets.randbelow", lambda _: next(draws))
    with TestClient(create_app()) as client:
        body = entity_data("New")
        body.pop("id")
        created = client.put("/entities/modelEntities/Raw/New", json=body)
        assert created.status_code == 200, created.text
        assert created.json()["item"]["entity"]["id"] == MAX_ENTITY_ID
        cloned = client.put(
            "/entities/clone",
            json={"locator": "modelEntities/Raw/New", "newLocator": "modelEntities/Raw/Copy"},
        )
        assert cloned.status_code == 200, cloned.text
        assert cloned.json()["items"][0]["entity"]["id"] == 1
        updated = client.patch(
            "/entities/modelEntities/Raw/New",
            json={"id": MAX_ENTITY_ID, "description": "Changed"},
        )
        assert updated.status_code == 200, updated.text
        rejected = client.patch("/entities/modelEntities/Raw/New", json={"id": 7})
        assert rejected.status_code == 400
        assert rejected.json()["code"] == "validation_error"
        moved = client.post(
            "/entities/move-single",
            json={"from": "modelEntities/Raw/New", "to": "modelEntities/Raw/Renamed"},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["item"]["entity"]["id"] == MAX_ENTITY_ID
        assert client.post("/model/save").status_code == 204
        monkeypatch.setattr("datam8.utils.ids.secrets.randbelow", original_randbelow)
        assert client.post("/model/reload").status_code == 200
    model = factory.get_model()
    assert model.modelEntities.get("Raw/Renamed").entity.id == MAX_ENTITY_ID
    assert model.modelEntities.get("Raw/Copy").entity.id == 1
    saved = json.loads((id_workspace.parent / "model/Raw/Renamed.json").read_text())
    assert saved["id"] == MAX_ENTITY_ID


@pytest.mark.parametrize(
    "entity_id,exit_code", [(0, 2), (-1, 2), (MAX_ENTITY_ID + 1, 2), (MAX_ENTITY_ID, 0)]
)
def test_cli_validation_checks_id_range(id_workspace, entity_id, exit_code):
    file = id_workspace.parent / "model/Raw/Invalid.json"
    file.write_text(json.dumps(entity_data("Invalid", entity_id)), encoding="utf-8")
    result = CliRunner().invoke(app, ["validate", "-s", str(id_workspace), "--json"])
    assert result.exit_code == exit_code, result.output
    assert json.loads(result.stdout)["ok"] == (exit_code == 0)


def test_duplicate_ids_fail_loading_and_cli_with_locators(id_workspace):
    file = id_workspace.parent / "model/Raw/Duplicate.json"
    file.write_text(json.dumps(entity_data("Duplicate")), encoding="utf-8")
    with pytest.raises(Datam8ValidationError, match="Duplicate IDs in modelEntities") as caught:
        asyncio.run(factory.load_model(id_workspace))
    assert set(caught.value.details["duplicates"][7]) == {
        "modelEntities/Raw/Existing",
        "modelEntities/Raw/Duplicate",
    }
    result = CliRunner().invoke(app, ["validate", "-s", str(id_workspace), "--json"])
    assert result.exit_code == 2, result.output
    message = json.loads(result.stdout)["error"]["message"]
    assert "7" in message and "Existing" in message and "Duplicate" in message


def test_save_rejects_duplicate_before_writing(id_workspace):
    model = factory.get_model()
    new = model.add_entity("modelEntities/Raw/New", entity_data())
    new.entity.id = 7
    with pytest.raises(Datam8ValidationError, match="Duplicate"):
        model.save()
    assert not new.source_file.exists()


@pytest.mark.parametrize("supplied_id", [None, 7])
def test_folder_create_clone_update_move_and_reload(id_workspace, supplied_id):
    factory.get_model()
    with TestClient(create_app()) as client:
        body = {"name": "Ignored"}
        if supplied_id is not None:
            body["id"] = supplied_id
        created = client.put("/entities/folders/Raw/New", json=body)
        assert created.status_code == 200, created.text
        saved = created.json()["item"]["entity"]
        folder_id = saved["id"]
        assert type(folder_id) is int and 1 <= folder_id <= MAX_ENTITY_ID
        assert folder_id not in (7, 11)
        assert saved["name"] == "New" and saved["path"] == "Raw/New"
        cloned = client.put(
            "/entities/clone",
            json={"locator": "folders/Raw/New", "newLocator": "folders/Raw/Copy"},
        )
        assert cloned.status_code == 200, cloned.text
        copy = cloned.json()["items"][0]["entity"]
        assert copy["id"] not in (7, 11, folder_id)
        assert copy["path"] == "Raw/Copy"
        updated = client.patch(
            "/entities/folders/Raw/New", json={"id": folder_id, "description": "Saved"}
        )
        assert updated.status_code == 200, updated.text
        assert client.patch("/entities/folders/Raw/New", json={"id": 7}).status_code == 400
        moved = client.post(
            "/entities/move-single",
            json={"from": "folders/Raw/New", "to": "folders/Raw/Renamed"},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["item"]["entity"]["id"] == folder_id
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
    model = factory.get_model()
    assert model.folders.get("Raw/Renamed").entity.id == folder_id
    assert model.folders.get("Raw/Copy").entity.id == copy["id"]
    persisted = json.loads((id_workspace.parent / "model/Raw/Renamed/.properties.json").read_text())
    assert persisted["folders"][0]["id"] == folder_id
    assert persisted["folders"][0]["description"] == "Saved"


def test_implicit_folders_use_allocator_once_per_path(id_workspace, monkeypatch):
    model = factory.get_model()
    model.add_entity("modelEntities/Raw/Second", entity_data("Second"))
    model.folders.remove("Raw")
    existing_count = len(model.folders)
    # All other implicit folders have already been created; only Raw is missing.
    draws = iter([6, MAX_ENTITY_ID - 1])
    monkeypatch.setattr("datam8.utils.ids.secrets.randbelow", lambda _: next(draws))
    factory.create_undefined_folders(model)
    assert model.folders.get("Raw").entity.id == MAX_ENTITY_ID
    assert len(model.folders) == existing_count + 1


@pytest.mark.parametrize("folder_id", [7, 11, MAX_ENTITY_ID + 1])
def test_folder_load_preserves_overlap_and_rejects_invalid_ids(id_workspace, folder_id):
    folder = id_workspace.parent / "model/Raw/Nested"
    folder.mkdir()
    (folder / ".properties.json").write_text(
        json.dumps(
            {
                "type": "folders",
                "folders": [{"id": folder_id, "name": "Nested", "path": "Raw/Nested"}],
            }
        ),
        encoding="utf-8",
    )
    if folder_id == 7:
        model = factory.get_model()
        assert (
            model.folders.get("Raw/Nested").entity.id
            == model.modelEntities.get("Raw/Existing").entity.id
        )
    else:
        with pytest.raises(Datam8ValidationError):
            factory.get_model()


def test_typed_creation_does_not_change_existing_identity(id_workspace):
    model = factory.get_model()
    for locator, target in (
        ("modelEntities/Raw/Existing", "modelEntities/Raw/Copy"),
        ("folders/Raw", "folders/Copy"),
    ):
        original = model.get_entity_by_locator(locator).entity
        old_id, old_name = original.id, original.name
        new = model.add_entity(target, original).entity
        assert new.id != old_id
        assert original.id == old_id and original.name == old_name


@pytest.mark.parametrize("locator", ["modelEntities/Raw/Existing", "folders/Raw"])
def test_nonfinite_patch_id_returns_validation_error(id_workspace, locator):
    factory.get_model()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.patch(
            f"/entities/{locator}",
            content='{"id":1e1000}',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "validation_error"


def test_migration_folders_avoid_model_and_folder_ids(tmp_path, monkeypatch):
    from datam8 import migration_v1, parser_v1
    from datam8_model import data_product as dp
    from datam8_model import zone as z

    module_path = tmp_path / "Raw/Product/Module"
    module_path.mkdir(parents=True)
    migration = migration_v1.MigrationV1(
        {"existing": parser_v1.ModelFileReference(id=7, path=tmp_path)}
    )
    draws = iter([6, MAX_ENTITY_ID - 1, MAX_ENTITY_ID - 1, 0])
    monkeypatch.setattr("datam8.utils.ids.secrets.randbelow", lambda _: next(draws))
    migration.create_properties_for_folders(
        zones=[z.Zone(name="Raw", targetName="raw", displayName="Raw")],
        data_products=[dp.DataProduct(name="Product", dataModules=[dp.DataModule(name="Module")])],
        output_path=tmp_path,
    )
    product = json.loads((module_path.parent / ".properties.json").read_text())
    module = json.loads((module_path / ".properties.json").read_text())
    assert product["folders"][0]["id"] == MAX_ENTITY_ID
    assert module["folders"][0]["id"] == 1
