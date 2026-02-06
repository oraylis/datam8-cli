from __future__ import annotations

import json
from pathlib import Path

from datam8.core.connectors.plugin_host import get_connector, load_connector_class


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_plugin_loader_supports_vendored_site_packages(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_root = plugin_dir / "connectors" / "testdep"
    plugin_root.mkdir(parents=True, exist_ok=True)

    _write(
        plugin_root / "plugin.json",
        json.dumps(
            {
                "pluginType": "connector",
                "id": "testdep",
                "displayName": "Testdep",
                "version": "0.1.0",
                "entrypoint": "datam8_plugins.testdep.connector:Connector",
                "capabilities": ["uiSchema", "validateConnection", "metadata"],
            }
        ),
    )
    _write(plugin_root / "src" / "datam8_plugins" / "testdep" / "__init__.py", "")
    _write(
        plugin_root / "deps" / "site-packages" / "vendored_dep.py",
        "VALUE = 'from-vendored'\n",
    )
    _write(
        plugin_root / "src" / "datam8_plugins" / "testdep" / "connector.py",
        """from __future__ import annotations
import vendored_dep

class Connector:
    @staticmethod
    def get_manifest() -> dict:
        return {"id": "testdep", "displayName": "Testdep", "version": vendored_dep.VALUE, "capabilities": ["uiSchema", "validateConnection", "metadata"]}

    @staticmethod
    def get_ui_schema() -> dict:
        return {"title": "Testdep", "authModes": [{"id": "none", "label": "None", "fields": []}]}

    @staticmethod
    def validate_connection(extended_properties: dict, secret_resolver) -> list:
        return []

    @staticmethod
    def test_connection(extended_properties: dict, secret_resolver) -> None:
        return None

    @staticmethod
    def list_schemas(extended_properties: dict, secret_resolver) -> list[str]:
        return []

    @staticmethod
    def list_tables(extended_properties: dict, secret_resolver, schema: str | None = None) -> list[dict]:
        return []

    @staticmethod
    def get_table_metadata(extended_properties: dict, secret_resolver, schema: str, table: str) -> dict:
        return {"schema": schema, "name": table, "columns": []}
""",
    )

    plugin = get_connector(plugin_dir=plugin_dir, connector_id="testdep")
    connector_cls = load_connector_class(plugin)
    manifest = connector_cls.get_manifest()
    assert manifest["version"] == "from-vendored"
