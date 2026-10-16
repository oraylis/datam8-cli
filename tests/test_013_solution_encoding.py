import json
from pathlib import Path

import pytest
from builtin_plugins.solution import create_solution
from fastapi.testclient import TestClient

from datam8 import config, factory
from datam8.api.app import create_app
from datam8.errors import Datam8ValidationError
from datam8.plugins.builtins.odcs import OdcsFile
from datam8.solution_encoding import ensure_utf8_solution

LEGACY = "für Größe €"


@pytest.fixture
def mixed_solution(tmp_path, builtin_environment):
    solution = create_solution(tmp_path, [(OdcsFile, "Contracts", {"path": "contract.json"})])
    settings = json.loads(solution.read_text(encoding="utf-8"))
    (tmp_path / "Base").rename(tmp_path / "Basis für Größe")
    (tmp_path / "Model").rename(tmp_path / "Modelle für Größe")
    settings.update(basePath="Basis für Größe", modelPath="Modelle für Größe")

    def write(path, content, encoding):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            (json.dumps(content, ensure_ascii=False, indent=2) + "\r\n").encode(encoding)
        )
        return path

    write(solution, settings, "cp1252")
    write(
        tmp_path / settings["basePath"] / "Properties.json",
        {"type": "properties", "properties": [{"name": "Comment", "displayName": LEGACY}]},
        "cp1252",
    )
    model = tmp_path / settings["modelPath"] / "Stage"
    write(
        model / ".properties.json",
        {
            "type": "folders",
            "folders": [{"id": 3, "name": "Stage", "path": "Stage", "description": LEGACY}],
        },
        "cp1252",
    )
    for identifier, name, description, encoding in [
        (1, "Legacy", LEGACY, "cp1252"),
        (2, "Unicode", "für 東京", "utf-8"),
    ]:
        write(
            model / f"{name}.json",
            {
                "id": identifier,
                "name": name,
                "description": description,
                "attributes": [
                    {
                        "name": "topic",
                        "ordinalNumber": 1,
                        "attributeType": "Defaultstring",
                        "dataType": {"type": "string", "nullable": True},
                        "dateAdded": "2026-01-01T00:00:00Z",
                    }
                ],
                "sources": [],
                "relationships": [],
                "transformations": [],
            },
            encoding,
        )
    for folder in ("Plugins", "Generate", "Output"):
        write(tmp_path / folder / "untouched.json", {"description": LEGACY}, "cp1252")
    (model / "function.py").write_bytes(b"# f\xfcr")
    return solution


def test_loading_mixed_solution_converts_only_legacy_json_once(mixed_solution, caplog):
    root = mixed_solution.parent
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }
    config.set_solution(mixed_solution)

    loaded = factory.create_model()

    assert loaded.modelEntities["modelEntities/Stage/Legacy"].entity.description == LEGACY
    assert loaded.modelEntities["modelEntities/Stage/Unicode"].entity.description == "für 東京"
    converted = []
    for path, (raw, modified) in before.items():
        backup = path.with_name(path.name + ".cp1252.bak")
        if backup.exists():
            converted.append(path)
            assert backup.read_bytes() == raw
            assert path.read_bytes() == raw.decode("cp1252").encode("utf-8")
        else:
            assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, modified)
    assert len(converted) == 4
    assert caplog.text.count("Converted Windows-1252 JSON") == 4
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }
    caplog.clear()

    with TestClient(create_app()) as client:
        assert client.post("/model/reload").status_code == 200
        response = client.get("/solution/full")
        assert response.status_code == 200, response.text
        descriptions = {
            item["entity"]["name"]: item["entity"]["description"]
            for item in response.json()["model_entities"]
        }
        assert descriptions == {"Legacy": LEGACY, "Unicode": "für 東京"}

    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in after} == after
    assert "Converted Windows-1252 JSON" not in caplog.text


@pytest.mark.parametrize("broken", [b'{"description":"\x81"}', b'{"description":"f\xfcr", broken}'])
def test_invalid_legacy_file_names_path_and_prevents_conversion(mixed_solution, broken):
    root = mixed_solution.parent
    invalid = root / "Modelle für Größe/Stage/Invalid.json"
    invalid.write_bytes(broken)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(Datam8ValidationError) as error:
        ensure_utf8_solution(mixed_solution)

    assert str(invalid) in str(error.value)
    assert {path: path.read_bytes() for path in before} == before
    assert not list(root.rglob("*.cp1252.bak"))


def test_existing_different_backup_is_not_overwritten(mixed_solution):
    backup = mixed_solution.with_name(mixed_solution.name + ".cp1252.bak")
    backup.write_bytes(b"existing backup")
    original = mixed_solution.read_bytes()

    with pytest.raises(Datam8ValidationError, match="Existing backup differs"):
        ensure_utf8_solution(mixed_solution)

    assert mixed_solution.read_bytes() == original
    assert backup.read_bytes() == b"existing backup"


def test_failed_replacement_keeps_original_and_can_retry(mixed_solution, monkeypatch):
    original = mixed_solution.read_bytes()
    with monkeypatch.context() as patch:

        def fail_replace(*args):
            raise PermissionError("replacement denied")

        patch.setattr(Path, "replace", fail_replace)
        with pytest.raises(Datam8ValidationError, match="replacement denied"):
            ensure_utf8_solution(mixed_solution)

    assert mixed_solution.read_bytes() == original
    assert mixed_solution.with_name(mixed_solution.name + ".cp1252.bak").read_bytes() == original
    assert not list(mixed_solution.parent.glob(f".{mixed_solution.name}.*"))

    ensure_utf8_solution(mixed_solution)

    assert mixed_solution.read_bytes() == original.decode("cp1252").encode("utf-8")
