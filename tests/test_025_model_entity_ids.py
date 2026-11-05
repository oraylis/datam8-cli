"""ID allocation, validation and persistence using disposable solutions."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from datam8 import config, factory, solution
from datam8.api.app import create_app
from datam8.app import app
from datam8.errors import Datam8ValidationError
from datam8.model import Locator
from datam8.model.ids import MAX_MODEL_ENTITY_ID


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
    (folder / "Existing.json").write_text(json.dumps(entity_data()), encoding="utf-8")
    monkeypatch.setattr(config, "solution_path", path, raising=False)
    monkeypatch.setattr(config, "solution_folder_path", tmp_path, raising=False)
    monkeypatch.setattr(config, "lazy", True)
    monkeypatch.setattr(config, "mode", config.RunMode.TEST)
    monkeypatch.setattr(factory, "_model", None)
    return path


def test_allocation_retries_loaded_and_reserved_ids(id_workspace, monkeypatch):
    model = factory.get_model()
    draws = iter([6, MAX_MODEL_ENTITY_ID - 1, MAX_MODEL_ENTITY_ID - 1, 0])
    monkeypatch.setattr("datam8.model.model.secrets.randbelow", lambda _: next(draws))
    assert model.get_next_model_id() == MAX_MODEL_ENTITY_ID
    assert model.get_next_model_id() == 1


def test_parallel_allocation_reserves_unique_safe_ids(id_workspace):
    model = factory.get_model()
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _: model.get_next_model_id(), range(500)))
    assert len(set(ids)) == 500
    assert 7 not in ids
    assert all(type(value) is int and 1 <= value <= MAX_MODEL_ENTITY_ID for value in ids)


def test_create_clone_update_move_and_reload_keep_actual_ids(id_workspace, monkeypatch):
    factory.get_model()
    draws = iter([MAX_MODEL_ENTITY_ID - 1, 0])
    monkeypatch.setattr("datam8.model.model.secrets.randbelow", lambda _: next(draws))
    with TestClient(create_app()) as client:
        body = entity_data("New")
        body.pop("id")
        created = client.put("/entities/modelEntities/Raw/New", json=body)
        assert created.status_code == 200, created.text
        assert created.json()["item"]["entity"]["id"] == MAX_MODEL_ENTITY_ID
        cloned = client.put(
            "/entities/clone",
            json={"locator": "modelEntities/Raw/New", "newLocator": "modelEntities/Raw/Copy"},
        )
        assert cloned.status_code == 200, cloned.text
        assert cloned.json()["items"][0]["entity"]["id"] == 1
        updated = client.patch(
            "/entities/modelEntities/Raw/New",
            json={"id": MAX_MODEL_ENTITY_ID, "description": "Changed"},
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
        assert moved.json()["item"]["entity"]["id"] == MAX_MODEL_ENTITY_ID
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
    model = factory.get_model()
    assert model.modelEntities.get("Raw/Renamed").entity.id == MAX_MODEL_ENTITY_ID
    assert model.modelEntities.get("Raw/Copy").entity.id == 1
    saved = json.loads((id_workspace.parent / "model/Raw/Renamed.json").read_text())
    assert saved["id"] == MAX_MODEL_ENTITY_ID


@pytest.mark.parametrize("entity_id", [0, -1, MAX_MODEL_ENTITY_ID + 1])
def test_cli_validation_rejects_invalid_ids(id_workspace, entity_id):
    file = id_workspace.parent / "model/Raw/Invalid.json"
    file.write_text(json.dumps(entity_data("Invalid", entity_id)), encoding="utf-8")
    result = CliRunner().invoke(app, ["validate", "-s", str(id_workspace), "--json"])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"


def test_duplicate_ids_fail_loading_and_cli_with_locators(id_workspace):
    file = id_workspace.parent / "model/Raw/Duplicate.json"
    file.write_text(json.dumps(entity_data("Duplicate")), encoding="utf-8")
    with pytest.raises(Datam8ValidationError, match="Duplicate model entity IDs") as caught:
        asyncio.run(factory.load_model(id_workspace))
    assert set(caught.value.details["duplicates"][7]) == {
        "modelEntities/Raw/Existing",
        "modelEntities/Raw/Duplicate",
    }
    result = CliRunner().invoke(app, ["validate", "-s", str(id_workspace), "--json"])
    assert result.exit_code == 2, result.output
    message = json.loads(result.stdout)["error"]["message"]
    assert "7" in message and "Existing" in message and "Duplicate" in message


def test_valid_mixed_ids_pass_cli_validation(id_workspace):
    file = id_workspace.parent / "model/Raw/New.json"
    file.write_text(json.dumps(entity_data("New", MAX_MODEL_ENTITY_ID)), encoding="utf-8")
    result = CliRunner().invoke(app, ["validate", "-s", str(id_workspace), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["item"]["valid"]


def test_source_import_uses_backend_id(tmp_path, builtin_environment, monkeypatch):
    from builtin_plugins.solution import create_solution
    from test_019_odcs import write_contract
    from test_019_odcs_cases import contract

    from datam8.plugins.builtins.odcs import OdcsFile

    write_contract(tmp_path / "contract.json", contract())
    path = create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.json"})])
    config.set_solution(path)
    factory.get_model()
    monkeypatch.setattr("datam8.model.model.secrets.randbelow", lambda _: MAX_MODEL_ENTITY_ID - 1)
    with TestClient(create_app()) as client:
        response = client.put(
            "/sources/Contracts/import",
            json={
                "locator": "modelEntities/Stage/Imported",
                "sourceLocation": "contract.json#customers",
            },
        )
        assert response.status_code == 200, response.text
    model = asyncio.run(factory.load_model(path))
    assert model.modelEntities.get("Stage/Imported").entity.id == MAX_MODEL_ENTITY_ID


def test_save_rejects_duplicate_before_writing(id_workspace):
    model = factory.get_model()
    new = model.add_entity("modelEntities/Raw/New", entity_data())
    new.entity.id = 7
    with pytest.raises(Datam8ValidationError, match="Duplicate"):
        model.save()
    assert not new.source_file.exists()


@pytest.mark.parametrize("persist_first", [False, True])
def test_rollback_deletes_only_created_entity(id_workspace, persist_first):
    model = factory.get_model()
    new = model.add_entity("modelEntities/Raw/New", entity_data())
    original = model.modelEntities.get("Raw/Existing")
    original.update(description="Unsaved draft")
    if persist_first:
        model.save("modelEntities/Raw/New")
    model.delete_entity(Locator.from_path("modelEntities/Raw/New"))
    model.save("modelEntities/Raw/New")
    assert not new.source_file.exists()
    assert new.locator not in model.modelEntities
    assert new.source_file not in model._model_files
    assert original.has_changed
    assert "description" not in json.loads(original.source_file.read_text())
    model.save()
    reloaded = asyncio.run(factory.load_model(id_workspace))
    assert len(reloaded.modelEntities) == 1
    assert reloaded.modelEntities.get("Raw/Existing").entity.description == "Unsaved draft"
