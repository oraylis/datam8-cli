# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import json
from pathlib import Path

from datam8.core.connectors.plugin_host import get_connector, load_connector_class

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "plugin_vendored_deps"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


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
        _read_fixture("testdep_connector.py"),
    )

    plugin = get_connector(plugin_dir=plugin_dir, connector_id="testdep")
    connector_cls = load_connector_class(plugin)
    manifest = connector_cls.get_manifest()
    assert manifest["version"] == "from-vendored"


def test_plugin_methods_support_lazy_vendored_imports(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_root = plugin_dir / "connectors" / "lazydep"
    plugin_root.mkdir(parents=True, exist_ok=True)

    _write(
        plugin_root / "plugin.json",
        json.dumps(
            {
                "pluginType": "connector",
                "id": "lazydep",
                "displayName": "Lazydep",
                "version": "0.1.0",
                "entrypoint": "datam8_plugins.lazydep.connector:Connector",
                "capabilities": ["uiSchema", "validateConnection", "metadata"],
            }
        ),
    )
    _write(plugin_root / "src" / "datam8_plugins" / "lazydep" / "__init__.py", "")
    _write(
        plugin_root / "deps" / "site-packages" / "vendored_lazy.py",
        "VALUE = 'lazy-ok'\n",
    )
    _write(
        plugin_root / "src" / "datam8_plugins" / "lazydep" / "connector.py",
        _read_fixture("lazydep_connector.py"),
    )

    plugin = get_connector(plugin_dir=plugin_dir, connector_id="lazydep")
    connector_cls = load_connector_class(plugin)
    connector_cls.test_connection({}, None)
    assert connector_cls.validate_connection({}, None) == []
