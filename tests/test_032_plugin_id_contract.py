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

import pytest

from datam8 import plugins
from datam8.plugins.manager import PluginManager


def test_builtin_manifest_lookup_uses_canonical_id() -> None:
    plugins.init_builtin_plugins()
    manifest = PluginManager().get_plugin_manifest("builtin:CsvFile")
    assert manifest.id == "builtin:CsvFile"


def test_builtin_manifest_lookup_rejects_legacy_name() -> None:
    plugins.init_builtin_plugins()

    with pytest.raises(Exception, match=r"Plugin `CsvFile` is not registered\."):
        PluginManager().get_plugin_manifest("CsvFile")


def test_init_builtin_plugins_rejects_legacy_sqlserver_name(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _record() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(plugins, "register_sql_server", _record)
    plugins.init_builtin_plugins(plugin_id="SQLServer")

    assert called is False


def test_init_builtin_plugins_accepts_canonical_sqlserver_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _record() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(plugins, "register_sql_server", _record)
    plugins.init_builtin_plugins(plugin_id="builtin:SQLServer")

    assert called is True
