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

from pytest_cases import parametrize_with_cases
from test_070_plugin_loader_cases import CasesVendoredPlugin

from datam8.core.connectors.plugin_host import get_connector, load_connector_class


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_fixture(path: Path, name: str) -> str:
    return (path / name).read_text(encoding="utf-8")


@parametrize_with_cases(
    "case_data",
    cases=CasesVendoredPlugin,
    glob="*manifest*",
)
def test_plugin_loader_supports_vendored_site_packages(case_data, tmp_path: Path) -> None:
    plugin_id, fixture_name, vendored_module, vendored_value, expected_manifest_version = case_data
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "plugin_vendored_deps"

    plugin_dir = tmp_path / "plugins"
    plugin_root = plugin_dir / "connectors" / plugin_id
    plugin_root.mkdir(parents=True, exist_ok=True)

    _write(
        plugin_root / "plugin.json",
        json.dumps(
            {
                "pluginType": "connector",
                "id": plugin_id,
                "displayName": plugin_id,
                "version": "0.1.0",
                "entrypoint": f"datam8_plugins.{plugin_id}.connector:Connector",
                "capabilities": ["uiSchema", "validateConnection", "metadata"],
            }
        ),
    )
    _write(plugin_root / "src" / "datam8_plugins" / plugin_id / "__init__.py", "")
    _write(
        plugin_root / "deps" / "site-packages" / vendored_module,
        f"VALUE = '{vendored_value}'\n",
    )
    _write(
        plugin_root / "src" / "datam8_plugins" / plugin_id / "connector.py",
        _read_fixture(fixture_dir, fixture_name),
    )

    plugin = get_connector(plugin_dir=plugin_dir, connector_id=plugin_id)
    connector_cls = load_connector_class(plugin)
    manifest = connector_cls.get_manifest()
    assert manifest["version"] == expected_manifest_version


@parametrize_with_cases(
    "case_data",
    cases=CasesVendoredPlugin,
    glob="*lazy*",
)
def test_plugin_methods_support_lazy_vendored_imports(case_data, tmp_path: Path) -> None:
    plugin_id, fixture_name, vendored_module, vendored_value = case_data
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "plugin_vendored_deps"

    plugin_dir = tmp_path / "plugins"
    plugin_root = plugin_dir / "connectors" / plugin_id
    plugin_root.mkdir(parents=True, exist_ok=True)

    _write(
        plugin_root / "plugin.json",
        json.dumps(
            {
                "pluginType": "connector",
                "id": plugin_id,
                "displayName": plugin_id,
                "version": "0.1.0",
                "entrypoint": f"datam8_plugins.{plugin_id}.connector:Connector",
                "capabilities": ["uiSchema", "validateConnection", "metadata"],
            }
        ),
    )
    _write(plugin_root / "src" / "datam8_plugins" / plugin_id / "__init__.py", "")
    _write(
        plugin_root / "deps" / "site-packages" / vendored_module,
        f"VALUE = '{vendored_value}'\n",
    )
    _write(
        plugin_root / "src" / "datam8_plugins" / plugin_id / "connector.py",
        _read_fixture(fixture_dir, fixture_name),
    )

    plugin = get_connector(plugin_dir=plugin_dir, connector_id=plugin_id)
    connector_cls = load_connector_class(plugin)
    connector_cls.test_connection({}, None)
    assert connector_cls.validate_connection({}, None) == []
