"""Fixed SQL quality contract through HTTP, persistence and target generation."""

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
    return {
        "id": "id_required",
        "execution": "enforcement",
        "expression": "Id IS NOT NULL",
        **patch,
    }


def test_fixed_quality_validation_is_atomic_before_coercion(quality_workspace):
    model = factory.get_model()
    quality = {"checks": [check()], "maxFailureRatePct": 5}
    url = "/entities/modelEntities/Raw/Existing"
    with TestClient(create_app()) as client:
        assert client.patch(url, json={"quality": quality}).status_code == 200
        for bad in [
            {"checks": [check(), check()]},
            {"checks": [check(expression="  ")]},
            {"checks": [check(definition={})]},
            {"checks": [check(severity="warn")]},
            {"checks": [check(severity=None)]},
            {"checks": [check(execution="unknown")]},
            {"checks": [check(sql="SELECT 1")]},
            {"checks": [check(onEmpty="evaluate")]},
            {"checks": [], "settings": {}},
            {"checks": [], "maxFailureRatePct": -1},
            {"checks": [], "maxFailureRatePct": True},
            {"checks": [], "maxFailureRatePct": "5"},
            {"checks": [], "maxFailureRatePct": None},
            {"checks": [], "references": {"ref": {"entityId": True}}},
            {"checks": [], "references": {"ref": {"entityId": "1"}}},
            {"checks": [], "references": {"ref": {"entityId": 1, "table": "x"}}},
        ]:
            response = client.patch(url, json={"quality": bad})
            assert response.status_code == 400, (bad, response.text)
            assert response.json()["code"] == "validation_error"
            assert (
                model.modelEntities.get("Raw/Existing").entity.quality.model_dump(
                    mode="json", exclude_none=True
                )
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
    object.__setattr__(
        wrapper.entity.quality,
        "checks",
        [*wrapper.entity.quality.checks, *wrapper.entity.quality.checks],
    )
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


def test_create_clone_and_unrelated_updates_preserve_optional_fields(quality_workspace):
    model = factory.get_model()
    with TestClient(create_app()) as client:
        payload = _entity_data("New")
        payload["quality"] = {"checks": [check()]}
        response = client.put("/entities/modelEntities/Raw/New", json=payload)
        assert response.status_code == 200, response.text
        response = client.put(
            "/entities/clone",
            json={"locator": "modelEntities/Raw/New", "newLocator": "modelEntities/Raw/Copy"},
        )
        assert response.status_code == 200, response.text
        assert (
            model.modelEntities.get("Raw/Copy").entity.quality.checks[0].expression
            == "Id IS NOT NULL"
        )
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


def test_sql_is_opaque_to_core_and_all_checks_can_be_deleted(quality_workspace):
    factory.get_model()
    url = "/entities/modelEntities/Raw/Existing"
    with TestClient(create_app()) as client:
        for expression in [
            "Id IS NULL OR COUNT(*) OVER (PARTITION BY Id) = 1",
            "invalid SQL is a target concern",
        ]:
            for execution in ["enforcement", "monitoring"]:
                quality = {"checks": [check(expression=expression, execution=execution)]}
                assert client.patch(url, json={"quality": quality}).status_code == 200
                assert client.post("/model/save").status_code == 204
                assert client.post("/model/reload").status_code == 200
                assert (
                    json.loads((quality_workspace.parent / "model/Raw/Existing.json").read_text())[
                        "quality"
                    ]
                    == quality
                )
        quality = {
            "checks": [
                check(
                    execution="monitoring",
                    expression="measured_value > 0",
                    sql="SELECT COUNT(*) AS checked_rows, COUNT(*) AS measured_value FROM {target}",
                    onEmpty="no_data",
                )
            ],
            "references": {"self": {"entityId": 1}},
        }
        assert client.patch(url, json={"quality": quality}).status_code == 200
        assert client.patch(url, json={"quality": {"checks": []}}).status_code == 200
        assert client.post("/model/save").status_code == 204
        assert client.post("/model/reload").status_code == 200
        assert factory.get_model().modelEntities.get("Raw/Existing").entity.quality.checks == []


def test_references_are_checked_against_active_model_entities(quality_workspace):
    from datam8.errors import Datam8ValidationError

    model = factory.get_model()
    wrapper = model.modelEntities.get("Raw/Existing")
    wrapper.update(quality={"checks": [], "references": {"missing": {"entityId": 999999}}})
    with pytest.raises(Datam8ValidationError, match="Invalid quality reference"):
        model.validate_quality()


def test_two_targets_interpret_the_same_sql_model_without_dqx_in_core(quality_workspace):
    from datam8_model.solution import GeneratorTarget

    model = factory.get_model()
    for name, prefix in [("engine_a", "ASSERT "), ("engine_b", "EXPECT ")]:
        directory = quality_workspace.parent / "generate" / name
        (directory / "__modules").mkdir(parents=True)
        (directory / (name + ".jinja2")).write_text("{{ data }}")
        (directory / "__modules/payload.py").write_text(
            "from pathlib import Path\nfrom datam8.generate import BasePayload,register_payload\n"
            f'@register_payload("{name}.jinja2")\ndef payload(model,cache):\n'
            " expression=model.modelEntities.get('Raw/Existing').entity.quality.checks[0].expression\n"
            f" return [BasePayload(data={prefix!r}+expression,output_path=Path('result.txt'))]\n"
        )
        model.solution.generatorTargets.append(
            GeneratorTarget(name=name, sourcePath=f"generate/{name}", outputPath=f"output/{name}")
        )
    with TestClient(create_app()) as client:
        assert (
            client.patch(
                "/entities/modelEntities/Raw/Existing", json={"quality": {"checks": [check()]}}
            ).status_code
            == 200
        )
        for name, prefix in [("engine_a", "ASSERT "), ("engine_b", "EXPECT ")]:
            response = client.post("/model/generate", json={"target": name, "cleanOutput": True})
            assert response.status_code == 200, response.text
            assert (
                quality_workspace.parent / f"output/{name}/result.txt"
            ).read_text().strip() == prefix + "Id IS NOT NULL"
