"""Opaque quality definitions through real HTTP, persistence and target generation."""

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
            "execution": "enforcement",
            "definition": {"check": {"function": "is_not_null", "arguments": {"column": "Id"}}},
        },
        **patch,
    )


def test_common_quality_validation_is_atomic(quality_workspace):
    factory.get_model()
    quality = {"checks": [check()], "settings": {"maxFailureRatePct": 5}}
    url = "/entities/modelEntities/Raw/Existing"
    with TestClient(create_app()) as client:
        assert client.patch(url, json={"quality": quality}).status_code == 200
        for bad in [
            {"checks": [check(), check()]},
            {"checks": [check(definition=[])]},
            {"checks": [check(type="dqx")]},
            {"checks": [check(execution="unknown")]},
            {"checks": [check()], "settings": {"maxFailureRatePct": -1}},
            {"checks": [check()], "referenceDatasets": {"ref": {"entityId": True}}},
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
        json.loads((quality_workspace.parent / "model/Raw/Existing.json").read_text())["quality"]
        == quality
    )


def test_generation_preflight_keeps_previous_output(quality_workspace):
    from datam8 import generate
    from datam8.errors import Datam8ValidationError
    from datam8_model.solution import GeneratorTarget

    model = factory.get_model()
    wrapper = model.modelEntities.get("Raw/Existing")
    wrapper.update(quality={"checks": [check()]})
    wrapper.entity.quality.checks = [*wrapper.entity.quality.checks, *wrapper.entity.quality.checks]
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


def test_quality_create_clone_and_attribute_changes_keep_opaque_definitions(quality_workspace):
    model = factory.get_model()
    with TestClient(create_app()) as client:
        payload = _entity_data("New")
        payload["quality"] = {"checks": [check()]}
        assert client.put("/entities/modelEntities/Raw/New", json=payload).status_code == 200
        assert (
            client.put(
                "/entities/clone",
                json={"locator": "modelEntities/Raw/New", "newLocator": "modelEntities/Raw/Copy"},
            ).status_code
            == 200
        )
        assert model.modelEntities.get("Raw/Copy").entity.quality.checks[0].id == "id_required"
        attributes = payload["attributes"]
        attributes[0]["dateDeleted"] = "2026-01-02T00:00:00Z"
        response = client.patch("/entities/modelEntities/Raw/New", json={"attributes": attributes})
        assert response.status_code == 200, response.text
        assert (
            model.modelEntities.get("Raw/New").entity.quality.model_dump(
                mode="json", exclude_none=True
            )
            == payload["quality"]
        )


def test_arbitrary_tool_dialects_and_nulls_roundtrip_and_can_be_deleted(quality_workspace):
    factory.get_model()
    url = "/entities/modelEntities/Raw/Existing"
    with TestClient(create_app()) as client:
        for definition in [
            {
                "check": {"function": "future_function", "arguments": [1, None]},
                "criticality": "other_engine_value",
            },
            {
                "assertion": "Id IS NOT NULL",
                "level": "fatal",
                "options": {"nested": [True, None]},
                "nullable": None,
            },
            {"check": "arbitrary", "user_metadata": {"datam8_check_id": "not a core concern"}},
        ]:
            quality = {
                "checks": [check(definition=definition)],
                "settings": {"engineOptions": None, "dependencies": {"non_python": "fixture"}},
                "referenceDatasets": {"file": {"uri": "memory://fixture", "option": None}},
            }
            for mode in ["enforcement", "monitoring"]:
                quality["checks"][0]["execution"] = mode
                response = client.patch(url, json={"quality": quality})
                assert response.status_code == 200, response.text
                assert client.post("/model/save").status_code == 204
                assert client.post("/model/reload").status_code == 200
                assert (
                    json.loads((quality_workspace.parent / "model/Raw/Existing.json").read_text())[
                        "quality"
                    ]
                    == quality
                )
        quality["checks"] = []
        assert client.patch(url, json={"quality": quality}).status_code == 200
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
        assert factory.get_model().modelEntities.get("Raw/Existing").entity.quality.checks == []


def test_two_target_payloads_interpret_different_definitions_without_core_changes(
    quality_workspace,
):
    from datam8_model.solution import GeneratorTarget

    model = factory.get_model()
    definitions = [
        (
            "engine_a",
            {"check": {"function": "is_not_null"}},
            "definition['check']['function']",
            "is_not_null",
        ),
        (
            "engine_b",
            {"assertion": {"expression": "Id IS NOT NULL"}},
            "definition['assertion']['expression']",
            "Id IS NOT NULL",
        ),
    ]
    for name, _, expression, _ in definitions:
        directory = quality_workspace.parent / "generate" / name
        (directory / "__modules").mkdir(parents=True)
        (directory / (name + ".jinja2")).write_text("{{ data }}")
        (directory / "__modules/payload.py").write_text(
            "from pathlib import Path\nfrom datam8.generate import BasePayload, register_payload\n"
            f"@register_payload('{name}.jinja2')\ndef payload(model, cache):\n"
            " definition = model.modelEntities.get('Raw/Existing').entity.quality.checks[0].definition\n"
            f" return [BasePayload(data={expression}, output_path=Path('result.txt'))]\n"
        )
        model.solution.generatorTargets.append(
            GeneratorTarget(name=name, sourcePath=f"generate/{name}", outputPath=f"output/{name}")
        )
    with TestClient(create_app()) as client:
        for name, definition, _, expected in definitions:
            assert (
                client.patch(
                    "/entities/modelEntities/Raw/Existing",
                    json={"quality": {"checks": [check(definition=definition)]}},
                ).status_code
                == 200
            )
            response = client.post("/model/generate", json={"target": name, "cleanOutput": True})
            assert response.status_code == 200, response.text
            assert (
                quality_workspace.parent / f"output/{name}/result.txt"
            ).read_text().strip() == expected
