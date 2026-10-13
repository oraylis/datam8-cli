from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from datam8 import factory
from datam8.api.app import create_app
from datam8.plugins.base import Plugin
from datam8.plugins.builtins.file import CsvFile
from datam8.plugins.navigation import normalize_source_item
from datam8_model.plugin import Capability


@pytest.mark.parametrize(
    "row,parent,kind,location",
    [
        ({"schema": "dbo"}, None, "SCHEMA", "dbo"),
        (
            {"schema": "dbo", "object": "customer", "type": "BASE TABLE"},
            "dbo",
            "BASE TABLE",
            "[dbo].[customer]",
        ),
        ({"schema": "schema]a", "object": "name]a"}, None, "OBJECT", "[schema]]a].[name]]a]"),
        (
            {"schema": "C:/csv", "object": "nested", "type": "DIRECTORY"},
            None,
            "DIRECTORY",
            "nested",
        ),
        (
            {"schema": "C:/csv/nested", "object": "orders.csv", "type": "FILE"},
            "nested",
            "FILE",
            "nested/orders.csv",
        ),
        ({"container": "raw"}, None, "CONTAINER", "raw"),
        (
            {"container": "raw", "name": "folder/file", "type": "BLOB"},
            "raw@folder",
            "BLOB",
            "raw@folder/file",
        ),
        (
            {"name": "remote", "type": "VIEW", "sourceLocation": " opaque#ü%2F "},
            None,
            "VIEW",
            " opaque#ü%2F ",
        ),
    ],
)
def test_legacy_rows_and_explicit_handles(row, parent, kind, location):
    original = dict(row)
    normalized = normalize_source_item(row, parent)
    assert normalized["type"] == kind
    assert normalized["sourceLocation"] == location
    assert normalized["name"]
    assert row == original


def test_explicit_source_override_is_retained():
    row = {
        "name": "object",
        "sourceLocation": "metadata#1",
        "sourceOverride": {"dataSource": "Read", "sourceLocation": "read://object"},
    }
    assert normalize_source_item(row)["sourceOverride"] == row["sourceOverride"]


class ConnectionCapabilities(CsvFile):
    def get_source_capabilities(self):
        capabilities = super().get_source_capabilities()
        capabilities["previewData"] = self.extended_properties.get("preview_enabled", False)
        return capabilities


def test_runtime_capabilities_are_enforced_without_preview_or_type_resolution(
    tmp_path, builtin_plugin, monkeypatch
):
    plugin = builtin_plugin(ConnectionCapabilities, {"path": str(tmp_path)})
    monkeypatch.setattr(factory, "get_plugin_for_data_source", lambda *_args, **_kwargs: plugin)
    monkeypatch.setattr(
        plugin, "preview_data", lambda *args, **kwargs: pytest.fail("Preview called")
    )
    monkeypatch.setattr(
        plugin, "resolve_source_type", lambda *args: pytest.fail("Type resolver called")
    )
    with TestClient(create_app()) as client:
        capabilities = client.get("/sources/ArbitraryName/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json() == {"listSource": True, "metadata": True, "previewData": False}
        assert (
            client.get(
                "/sources/ArbitraryName/locations/preview", params={"source_location": "file.csv"}
            ).status_code
            == 400
        )
        # A missing optional hook stays on the original metadata fallback.
        monkeypatch.setattr(factory, "get_model", lambda: object())
        response = client.get(
            "/sources/ArbitraryName/locations/import-description",
            params={"source_location": "file.csv"},
        )
        assert response.status_code == 200 and response.json() == {"entity": None}


def test_unimplemented_methods_are_not_advertised():
    class MetadataOnly(CsvFile):
        list_source = Plugin.list_source
        preview_data = Plugin.preview_data

        @classmethod
        def manifest(cls):
            return CsvFile.manifest().model_copy(
                update={"capabilities": [Capability.METADATA, Capability.PREVIEW_DATA]}
            )

    plugin = object.__new__(MetadataOnly)
    assert plugin.get_source_capabilities() == {
        "listSource": False,
        "metadata": True,
        "previewData": False,
    }
