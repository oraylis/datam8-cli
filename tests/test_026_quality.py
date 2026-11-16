"""Quality validation through actual HTTP and persisted disposable models."""

import json

import pytest
from fastapi.testclient import TestClient
from test_025_model_entity_ids import entity_data as _entity_data
from test_025_model_entity_ids import id_workspace as _id_workspace

from datam8 import factory
from datam8.api.app import create_app


@pytest.fixture
def quality_workspace(tmp_path, monkeypatch):
    return _id_workspace.__wrapped__(tmp_path, monkeypatch)


def check(**patch):
    return dict(
        {
            "id": "id_required",
            "type": "not_null",
            "attribute": "Id",
            "execution": "enforcement",
            "severity": "error",
        },
        **patch,
    )


def test_quality_http_roundtrip_and_rejection_are_atomic(quality_workspace):
    factory.get_model()
    with TestClient(create_app()) as client:
        quality = {"checks": [check()], "settings": {"maxFailureRatePct": 5}}
        url = "/entities/modelEntities/Raw/Existing"
        assert client.patch(url, json={"quality": quality}).status_code == 200
        for bad in [
            {"checks": [check(attribute="Missing")]},
            {"checks": [check(), check()]},
            {"checks": [check(type="range", parameters={"min": 4, "max": 2})]},
            {
                "checks": [
                    check(type="freshness", execution="monitoring", parameters={"maxAgeSeconds": 1})
                ]
            },
            {"checks": [check(severity="warn")]},
        ]:
            response = client.patch(url, json={"quality": bad})
            assert response.status_code == 400, response.text
            assert response.json()["code"] == "validation_error"
            assert (
                factory.get_model()
                .modelEntities.get("Raw/Existing")
                .entity.quality.model_dump(mode="json", exclude_none=True)
                == quality
            )
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
        assert (
            factory.get_model().modelEntities.get("Raw/Existing").entity.quality.checks[0].id
            == "id_required"
        )
    saved = json.loads((quality_workspace.parent / "model/Raw/Existing.json").read_text())
    assert saved["quality"] == quality


def test_generation_preflight_keeps_previous_output(quality_workspace):
    from datam8 import generate
    from datam8.errors import Datam8ValidationError

    model = factory.get_model()
    wrapper = model.modelEntities.get("Raw/Existing")
    wrapper.update(quality={"checks": [check()]})
    # Nested edits by target/source code must be revalidated before deleting output.
    wrapper.entity.attributes[0].name = "Changed"
    from datam8_model.solution import GeneratorTarget

    model.solution.generatorTargets.append(
        GeneratorTarget(name="docs", sourcePath="generate/docs", outputPath="output/docs")
    )
    output = quality_workspace.parent / "output/docs/keep.txt"
    output.parent.mkdir(parents=True)
    output.write_text("existing")
    with pytest.raises(Datam8ValidationError):
        generate.generate_output(
            model, target="docs", payloads=[], generate_all=False, clean_output=True
        )
    assert output.read_text() == "existing"


def test_quality_create_clone_and_deleted_reference(quality_workspace):
    model = factory.get_model()
    with TestClient(create_app()) as client:
        payload = _entity_data("New")
        payload["quality"] = {"checks": [check(severity="warn")]}
        rejected = client.put("/entities/modelEntities/Raw/New", json=payload)
        assert rejected.status_code == 400, rejected.text
        assert not model.has_locator("modelEntities/Raw/New")
        payload["quality"] = {"checks": [check()]}
        created = client.put("/entities/modelEntities/Raw/New", json=payload)
        assert created.status_code == 200, created.text
        cloned = client.put(
            "/entities/clone",
            json={"locator": "modelEntities/Raw/New", "newLocator": "modelEntities/Raw/Copy"},
        )
        assert cloned.status_code == 200, cloned.text
        assert model.modelEntities.get("Raw/Copy").entity.quality.checks[0].id == "id_required"
        attributes = payload["attributes"]
        attributes[0]["dateDeleted"] = "2026-01-02T00:00:00Z"
        deleted = client.patch("/entities/modelEntities/Raw/New", json={"attributes": attributes})
        assert deleted.status_code == 400, deleted.text
        assert model.modelEntities.get("Raw/New").entity.attributes[0].dateDeleted is None
