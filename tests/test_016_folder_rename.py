import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app


@pytest.mark.parametrize("with_entities", [False, True], ids=["metadata-only", "with-entities"])
@pytest.mark.parametrize("extra_file", [False, True], ids=["empty-source", "unrelated-file"])
def test_folder_rename_moves_root_and_child_metadata(
    tmp_path, monkeypatch, with_entities, extra_file
):
    def write_json(relative_path, content):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content), encoding="utf-8")
        return target

    solution_path = write_json(
        "Rename.dm8s",
        {
            "schemaVersion": "2.0.0",
            "basePath": "Base",
            "modelPath": "Model",
            "pluginsPath": "Plugins",
            "generatorTargets": [
                {"name": "test", "sourcePath": "Generate", "outputPath": "Output"}
            ],
        },
    )
    write_json(
        "Base/DataProducts.json",
        {
            "type": "dataProducts",
            "dataProducts": [{"name": "Product", "dataModules": [{"name": "Module"}]}],
        },
    )
    write_json(
        "Base/Properties.json",
        {
            "type": "properties",
            "properties": [{"name": "write_mode", "displayName": "Write mode"}],
        },
    )
    write_json(
        "Base/Zones.json",
        {
            "type": "zones",
            "zones": [{"name": "Core", "targetName": "core", "displayName": "Core"}],
        },
    )
    write_json(
        "Base/PropertyValues.json",
        {
            "type": "propertyValues",
            "propertyValues": [{"property": "write_mode", "name": "merge"}],
        },
    )
    original_meta = {
        "id": 201,
        "name": "Before",
        "path": "Core/Before",
        "displayName": "Folder label",
        "description": "Original description",
        "dataProduct": "Product",
        "dataModule": "Module",
        "properties": [{"property": "write_mode", "value": "merge"}],
    }
    child_meta = {**original_meta, "id": 202, "name": "Details", "path": "Core/Before/Details"}
    neighbour_meta = {
        **original_meta,
        "id": 203,
        "name": "BeforeArchive",
        "path": "Core/BeforeArchive",
    }
    write_json(
        "Model/Core/Before/.properties.json", {"type": "folders", "folders": [original_meta]}
    )
    write_json(
        "Model/Core/Before/Details/.properties.json", {"type": "folders", "folders": [child_meta]}
    )
    neighbour = write_json(
        "Model/Core/BeforeArchive/.properties.json",
        {"type": "folders", "folders": [neighbour_meta]},
    )
    neighbour_bytes = neighbour.read_bytes()
    entity = {
        "id": 1,
        "name": "Customer",
        "attributes": [
            {
                "ordinalNumber": 1,
                "name": "Id",
                "attributeType": "ID",
                "dataType": {"type": "int", "nullable": False},
                "dateAdded": "2026-01-01T00:00:00Z",
            }
        ],
        "sources": [],
        "relationships": [],
        "transformations": [],
    }
    if with_entities:
        write_json("Model/Core/Before/Customer.json", entity)
        write_json("Model/Core/Before/Details/Customer.json", {**entity, "id": 2})
    if extra_file:
        (tmp_path / "Model/Core/Before/notes.txt").write_text("Keep this file", encoding="utf-8")

    monkeypatch.setattr(config, "solution_path", solution_path)
    monkeypatch.setattr(config, "solution_folder_path", tmp_path)
    monkeypatch.setattr(config, "lazy", True)
    monkeypatch.setattr(factory, "_model", asyncio.run(factory.load_model(solution_path)))
    client = TestClient(create_app())

    # Same order as the Folder editor: save metadata first, then move and save the tree.
    patched_meta = {**original_meta, "description": "Edited while renaming"}
    response = client.patch("/entities/folders/Core/Before", json=patched_meta)
    assert response.status_code == 200, response.text
    assert client.post("/model/save").status_code == 204
    response = client.post(
        "/entities/move",
        json={
            "from": "modelEntities/Core/Before/",
            "to": "modelEntities/Core/After/",
        },
    )
    assert response.status_code == 200, response.text
    assert factory.get_model().has_locator("folders/Core/After")
    response = client.post("/model/save")
    assert response.status_code == 204, response.text

    target = tmp_path / "Model/Core/After"
    expected_root = {**patched_meta, "name": "After", "path": "Core/After"}
    expected_child = {**child_meta, "path": "Core/After/Details"}
    assert json.loads((target / ".properties.json").read_text())["folders"] == [expected_root]
    assert json.loads((target / "Details/.properties.json").read_text())["folders"] == [
        expected_child
    ]
    assert neighbour.read_bytes() == neighbour_bytes
    if with_entities:
        assert json.loads((target / "Customer.json").read_text())["id"] == 1
        assert json.loads((target / "Details/Customer.json").read_text())["id"] == 2
    source = tmp_path / "Model/Core/Before"
    if extra_file:
        assert [file.name for file in source.iterdir()] == ["notes.txt"]
        assert (source / "notes.txt").read_text() == "Keep this file"
    else:
        assert not source.exists()

    assert client.post("/model/reload").status_code == 200
    reloaded = factory.get_model()
    assert not reloaded.has_locator("folders/Core/Before")
    for locator, meta, file in [
        ("folders/Core/After", expected_root, target / ".properties.json"),
        ("folders/Core/After/Details", expected_child, target / "Details/.properties.json"),
    ]:
        wrapper = reloaded.folders[locator]
        assert wrapper.entity.model_dump(exclude_none=True) == meta
        assert wrapper.source_file == file
    if with_entities:
        assert reloaded.modelEntities["Core/After/Customer"].source_file == target / "Customer.json"
        assert not reloaded.has_locator("modelEntities/Core/Before/Customer")
    assert reloaded.get_unsaved_entities() == ([], [])
