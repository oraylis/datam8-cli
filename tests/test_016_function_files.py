import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app


@pytest.fixture
def function_solution(tmp_path, monkeypatch):
    root = tmp_path.resolve()

    def write(relative, content):
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(content), encoding="utf-8")
        return file

    solution = write(
        "Functions.dm8s",
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
    write(
        "Base/Zones.json",
        {
            "type": "zones",
            "zones": [{"name": "Core", "targetName": "core", "displayName": "Core"}],
        },
    )
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
    monkeypatch.setattr(config, "solution_path", solution)
    monkeypatch.setattr(config, "solution_folder_path", root)
    monkeypatch.setattr(config, "lazy", True)
    monkeypatch.setattr(factory, "_model", None)

    def load(source, actual_source=None, shared=False, missing=False):
        transformations = [
            {"stepNo": 1, "kind": "function", "name": "Clean", "function": {"source": source}},
            {"stepNo": 2, "kind": "function", "name": "Again", "function": {"source": source}},
            {"stepNo": 3, "kind": "builtin", "name": "Builtin"},
        ]
        write("Model/Core/Customer.json", {**entity, "transformations": transformations})
        file = (root / "Model/Core" / (actual_source or source)).resolve()
        if not missing:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("def transform(df):\n    return df\n", encoding="utf-8")
        if shared:
            write(
                "Model/Core/Neighbour.json",
                {
                    **entity,
                    "id": 2,
                    "name": "Neighbour",
                    "transformations": [
                        {
                            "stepNo": 1,
                            "kind": "function",
                            "name": "Shared",
                            "function": {"source": actual_source or source},
                        }
                    ],
                },
            )
        factory._model = asyncio.run(factory.load_model(solution))
        return TestClient(create_app()), root, file

    return load


LAYOUTS = [
    ("clean.py", "clean.py"),
    ("Customer/clean.py", "Customer/clean.py"),
    ("clean.py", "Customer/clean.py"),
    ("scripts/clean.py", "scripts/clean.py"),
]


@pytest.mark.parametrize(
    "source, actual_source", LAYOUTS, ids=["direct", "nested", "legacy", "other-nested"]
)
def test_rename_keeps_function_files_and_reload_resolves_them(
    function_solution, source, actual_source
):
    client, root, file = function_solution(source, actual_source)
    original = file.read_bytes()
    response = client.post(
        "/entities/rename", json={"from": "modelEntities/Core/Customer", "to": "Renamed"}
    )
    assert response.status_code == 200, response.text
    response = client.post("/model/save")
    assert response.status_code == 204, response.text
    assert not (root / "Model/Core/Customer.json").exists()
    assert file.read_bytes() == original
    saved = json.loads((root / "Model/Core/Renamed.json").read_text())
    assert saved["transformations"][0]["function"]["source"] == actual_source
    assert saved["transformations"][1]["function"]["source"] == actual_source
    assert not (root / "Model/Core/Renamed").exists()
    assert client.post("/model/reload").status_code == 200
    response = client.get("/functions/1/1")
    assert response.status_code == 200, response.text
    assert response.json()["item"]["source_code"] == file.read_text(encoding="utf-8")
    response = client.get("/functions/1")
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 2
    assert (
        client.post("/functions/1/1", json={"sourceCode": "# edited after rename\n"}).status_code
        == 204
    )
    assert file.read_text() == "# edited after rename\n"


@pytest.mark.parametrize(
    "source, actual_source", LAYOUTS, ids=["direct", "nested", "legacy", "other-nested"]
)
@pytest.mark.parametrize("missing", [False, True], ids=["existing", "missing"])
def test_delete_entity_removes_only_its_function_files(
    function_solution, source, actual_source, missing
):
    client, root, file = function_solution(source, actual_source, missing=missing)
    unrelated = root / "Model/Core/keep.py"
    unrelated.write_text("# unrelated", encoding="utf-8")
    response = client.delete("/entities/modelEntities/Core/Customer")
    assert response.status_code == 200, response.text
    assert client.post("/model/save").status_code == 204
    assert not (root / "Model/Core/Customer.json").exists()
    assert not file.exists()
    assert unrelated.read_text() == "# unrelated"
    if file.parent != unrelated.parent:
        assert not file.parent.exists()
    assert client.post("/model/reload").status_code == 200


@pytest.mark.parametrize(
    "source, actual_source", LAYOUTS, ids=["direct", "nested", "legacy", "other-nested"]
)
def test_delete_preserves_function_referenced_by_another_entity(
    function_solution, source, actual_source
):
    client, root, file = function_solution(source, actual_source, shared=True)
    original = file.read_bytes()
    assert client.delete("/entities/modelEntities/Core/Customer").status_code == 200
    assert client.post("/model/save").status_code == 204
    assert file.read_bytes() == original
    assert (root / "Model/Core/Neighbour.json").exists()
    assert client.post("/model/reload").status_code == 200
    assert client.get("/functions/2/1").status_code == 200
    assert client.delete("/entities/modelEntities/Core/Neighbour").status_code == 200
    assert client.post("/model/save").status_code == 204
    assert not file.exists()


def test_delete_preserves_sources_outside_entity_directory(function_solution):
    client, root, file = function_solution("../shared.py")
    assert client.delete("/entities/modelEntities/Core/Customer").status_code == 200
    assert client.post("/model/save").status_code == 204
    assert file.read_text().startswith("def transform")
    assert not (root / "Model/Core/Customer.json").exists()


def test_folder_delete_removes_referenced_functions_and_empty_directories(function_solution):
    client, root, file = function_solution("Customer/clean.py")
    assert client.delete("/entities/modelEntities/Core/").status_code == 200
    assert client.post("/model/save").status_code == 204
    assert not file.exists()
    assert not (root / "Model/Core").exists()


def test_direct_source_takes_precedence_over_legacy_folder(function_solution):
    client, root, file = function_solution("clean.py")
    legacy = root / "Model/Core/Customer/clean.py"
    legacy.parent.mkdir()
    legacy.write_text("# keep unreferenced legacy file", encoding="utf-8")
    assert client.delete("/entities/modelEntities/Core/Customer").status_code == 200
    assert client.post("/model/save").status_code == 204
    assert not file.exists()
    assert legacy.read_text() == "# keep unreferenced legacy file"


def test_entity_move_preserves_target_functions_on_save(function_solution):
    client, root, file = function_solution("Customer/clean.py")
    # Keep one step to exercise a physical move, rather than repeated references.
    wrapper = factory.get_model().modelEntities["Core/Customer"]
    wrapper.entity.transformations = wrapper.entity.transformations[:1]
    original = file.read_bytes()
    response = client.post(
        "/entities/move",
        json={
            "from": "modelEntities/Core/Customer",
            "to": "modelEntities/Core/Archive/Customer",
        },
    )
    assert response.status_code == 200, response.text
    assert client.post("/model/save").status_code == 204
    target = root / "Model/Core/Archive/Customer/clean.py"
    assert target.read_bytes() == original
    assert not file.exists()
    assert client.post("/model/reload").status_code == 200
    assert client.get("/functions/1/1").status_code == 200


def test_move_does_not_delete_unreferenced_legacy_fallback(function_solution):
    client, root, _ = function_solution("clean.py")
    legacy = root / "Model/Core/Customer/clean.py"
    legacy.parent.mkdir()
    legacy.write_text("# unreferenced fallback", encoding="utf-8")
    wrapper = factory.get_model().modelEntities["Core/Customer"]
    wrapper.entity.transformations = wrapper.entity.transformations[:1]
    response = client.post(
        "/entities/move",
        json={
            "from": "modelEntities/Core/Customer",
            "to": "modelEntities/Core/Archive/Customer",
        },
    )
    assert response.status_code == 200, response.text
    assert client.post("/model/save").status_code == 204
    assert legacy.read_text() == "# unreferenced fallback"
    assert (root / "Model/Core/Archive/clean.py").exists()
