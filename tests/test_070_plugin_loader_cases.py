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

from pytest_cases import parametrize


class CasesVendoredPlugin:
    @parametrize(
        "plugin_id, fixture_name, vendored_module, vendored_value, expected_manifest_version",
        [
            (
                "testdep",
                "testdep_connector.py",
                "vendored_dep.py",
                "from-vendored",
                "from-vendored",
            ),
        ],
    )
    def case_manifest_uses_vendored_import(
        self,
        plugin_id,
        fixture_name,
        vendored_module,
        vendored_value,
        expected_manifest_version,
    ):
        return (
            plugin_id,
            fixture_name,
            vendored_module,
            vendored_value,
            expected_manifest_version,
        )

    @parametrize(
        "plugin_id, fixture_name, vendored_module, vendored_value",
        [
            ("lazydep", "lazydep_connector.py", "vendored_lazy.py", "lazy-ok"),
        ],
    )
    def case_lazy_methods_use_vendored_import(
        self,
        plugin_id,
        fixture_name,
        vendored_module,
        vendored_value,
    ):
        return plugin_id, fixture_name, vendored_module, vendored_value
