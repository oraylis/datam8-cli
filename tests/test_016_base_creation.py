import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app
from datam8.model import EntityRepository, EntityWrapper, Locator, Model
from datam8.model.model import class_from_type
from datam8_model import base as b
from datam8_model.solution import GeneratorTarget, Solution

BASE_ITEMS = {
    "attributeTypes": {"name": "Existing", "displayName": "Existing", "defaultType": "string"},
    "dataTypes": {"name": "Existing", "targets": {"test": "string"}},
    "dataSources": {"name": "Existing", "type": "TestType", "extendedProperties": {}},
    "dataSourceTypes": {
        "name": "Existing",
        "dataTypeMapping": [{"sourceType": "string", "targetType": "string"}],
        "connectionProperties": [{"name": "host", "type": "string", "required": True}],
        "authModes": [{"name": "default", "required": ["host"], "optional": []}],
    },
    "dataProducts": {"name": "Existing", "dataModules": [{"name": "Module"}]},
    "zones": {"name": "Existing", "targetName": "existing", "displayName": "Existing"},
    "properties": {"name": "Existing", "displayName": "Existing", "scopes": []},
    "propertyValues": {"name": "Existing", "property": "Priority"},
}


@pytest.fixture
def base_model(tmp_path, monkeypatch):
    solution = Solution(
        schemaVersion="2.0.0",
        basePath=Path("Base"),
        modelPath=Path("Model"),
        pluginsPath=Path("Plugins"),
        generatorTargets=[
            GeneratorTarget(name="test", sourcePath=Path("Generate"), outputPath=Path("Output"))
        ],
    )
    model = Model(solution, **{t.value: EntityRepository({}, t.value) for t in b.EntityType})
    monkeypatch.setattr(config, "solution_folder_path", tmp_path)
    monkeypatch.setattr(factory, "get_model", lambda: model)
    return model, TestClient(create_app())


def seed(model, root, relative, kind, rows):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"type": kind, kind: rows}), encoding="utf-8")
    for row in rows:
        locator = Locator.from_path(
            f"{kind}/{row['property']}/{row['name']}"
            if kind == "propertyValues"
            else f"{kind}/{row['name']}"
        )
        model[kind].add(
            locator,
            EntityWrapper(
                locator=locator,
                source_file=target,
                entity=class_from_type(b.EntityType(kind)).from_dict(row),
                resolved=True,
            ),
        )
        model.update_file_reference(_type=b.EntityType(kind), file_path=target, locators=[locator])
    return target


@pytest.mark.parametrize("kind", BASE_ITEMS)
@pytest.mark.parametrize("placement", ["standard", "custom", "multiple"])
def test_create_appends_to_selected_collection(base_model, tmp_path, kind, placement):
    model, client = base_model
    filename = f"{kind[0].upper()}{kind[1:]}.json"
    relative = f"Base/{filename}" if placement == "standard" else "Base/Custom/Selected values.json"
    target = seed(model, tmp_path, relative, kind, [BASE_ITEMS[kind]])
    if placement == "multiple":
        seed(model, tmp_path, f"Base/{filename}", kind, [{**BASE_ITEMS[kind], "name": "Other"}])
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    body = {**BASE_ITEMS[kind], "name": "New"}
    locator = f"{kind}/Priority/New" if kind == "propertyValues" else f"{kind}/New"

    response = client.put(f"/entities/{locator}", params={"sourceFile": relative}, json=body)

    assert response.status_code == 200, response.text
    assert model.get_entity_by_locator(locator).source_file == target
    assert target.read_bytes() == before[target]  # PUT only changes in-memory state.
    assert client.post("/model/save").status_code == 204
    rows = json.loads(target.read_text(encoding="utf-8"))[kind]
    assert [row["name"] for row in rows] == ["Existing", "New"]
    assert {p for p in tmp_path.rglob("*.json")} == set(before)
    for other, contents in before.items():
        if other != target:
            assert other.read_bytes() == contents
    assert model.get_unsaved_entities() == ([], [])


def test_property_values_new_property_and_same_name_keep_selected_file(base_model, tmp_path):
    model, client = base_model
    relative = "Base/Custom/Values.json"
    target = seed(
        model, tmp_path, relative, "propertyValues", [{"property": "Priority", "name": "Default"}]
    )
    response = client.put(
        "/entities/propertyValues/Status/Default",
        params={"sourceFile": relative},
        json={"property": "Status", "name": "Default"},
    )
    assert response.status_code == 200, response.text
    assert client.post("/model/save").status_code == 204
    assert json.loads(target.read_text(encoding="utf-8"))["propertyValues"] == [
        {"property": "Priority", "name": "Default"},
        {"property": "Status", "name": "Default"},
    ]
    # Subsequent PATCH continues to use the same source file.
    assert (
        client.patch(
            "/entities/propertyValues/Status/Default", json={"displayName": "Changed"}
        ).status_code
        == 200
    )
    assert client.post("/model/save").status_code == 204
    assert (
        json.loads(target.read_text(encoding="utf-8"))["propertyValues"][1]["displayName"]
        == "Changed"
    )
    assert list(tmp_path.rglob("*.json")) == [target]


@pytest.mark.parametrize(
    "relative",
    [
        "",
        "Base/Missing.json",
        "../Outside.json",
        "Outside.json",
        "Base/Wrong.json",
        "Base/Invalid.json",
        "absolute",
    ],
)
def test_invalid_target_does_not_mutate_model(base_model, tmp_path, relative):
    model, client = base_model
    (tmp_path / "Base").mkdir()
    (tmp_path / "Base/Wrong.json").write_text(
        json.dumps({"type": "zones", "zones": [BASE_ITEMS["zones"]]}), encoding="utf-8"
    )
    (tmp_path / "Base/Invalid.json").write_text("not JSON", encoding="utf-8")
    (tmp_path / "Outside.json").write_text(
        json.dumps({"type": "dataTypes", "dataTypes": []}), encoding="utf-8"
    )
    if relative == "absolute":
        relative = str(tmp_path / "Base/Wrong.json")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}

    response = client.put(
        "/entities/dataTypes/New",
        params={"sourceFile": relative},
        json={"name": "New", "targets": {}},
    )

    assert response.status_code == 400, response.text
    assert not model.has_locator("dataTypes/New")
    assert model._model_files == {}
    assert model.get_unsaved_entities() == ([], [])
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("kind", ["modelEntities", "folders", "dataModules"])
def test_explicit_target_rejects_non_collection_types(base_model, kind):
    model, client = base_model
    response = client.put(
        f"/entities/{kind}/New", params={"sourceFile": "Base/Anything.json"}, json={}
    )
    assert response.status_code == 400, response.text
    assert model._model_files == {}


@pytest.mark.parametrize("kind", BASE_ITEMS)
def test_create_without_target_retains_default_placement(base_model, tmp_path, kind):
    model, client = base_model
    body = {**BASE_ITEMS[kind], "name": "New"}
    locator = f"{kind}/Priority/New" if kind == "propertyValues" else f"{kind}/New"
    response = client.put(f"/entities/{locator}", json=body)
    assert response.status_code == 200, response.text
    expected = tmp_path / "Base"
    if kind == "propertyValues":
        expected /= "Priority"
    expected /= f"{kind[0].upper()}{kind[1:]}.json"
    assert model.get_entity_by_locator(locator).source_file == expected
    assert client.post("/model/save").status_code == 204
    assert json.loads(expected.read_text(encoding="utf-8"))[kind][0]["name"] == "New"
