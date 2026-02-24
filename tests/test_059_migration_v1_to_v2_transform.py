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

from datam8.core.migration_v1_to_v2_transform import (
    build_data_source_types,
    build_generator_targets,
    build_zone_entries,
    convert_base_attribute_types,
    convert_base_data_types,
)


def test_build_zone_entries_uses_config_order_and_default_fallback() -> None:
    payload = build_zone_entries({"core", "raw", "stage"})
    assert [row["name"] for row in payload["zones"]] == ["raw", "stage", "core"]

    fallback_payload = build_zone_entries(set())
    assert len(fallback_payload["zones"]) == 1
    assert fallback_payload["zones"][0]["name"] == "stage"
    assert fallback_payload["zones"][0]["targetName"] == "010-Stage"


def test_convert_base_attribute_types_normalizes_unitfree_and_description() -> None:
    warnings: list[str] = []
    payload = {
        "items": [
            {
                "name": "Amount",
                "displayName": "Amount",
                "purpose": "Business amount",
                "description": "No unit in source",
                "hasUnit": "UnitFree",
            }
        ]
    }

    converted = convert_base_attribute_types(payload, warnings)
    first = converted["attributeTypes"][0]

    assert first["hasUnit"] == "NoUnit"
    assert first["description"] == "Business amount\nNo unit in source"
    assert warnings == []


def test_convert_base_type_lists_do_not_fall_back_to_defaults() -> None:
    warnings: list[str] = []
    attrs = convert_base_attribute_types({"items": []}, warnings)
    data_types = convert_base_data_types({"items": []}, warnings)

    assert attrs["attributeTypes"] == []
    assert data_types["dataTypes"] == []


def test_build_data_source_types_uses_fallback_mapping_when_missing() -> None:
    warnings: list[str] = []
    out_data_sources = {
        "dataSources": [
            {
                "name": "A",
                "type": "SqlServer",
                "dataTypeMapping": [
                    {"sourceType": "nvarchar", "targetType": "string"},
                    {"sourceType": "nvarchar", "targetType": "string"},
                ],
            },
            {"name": "B", "type": "Csv"},
        ]
    }

    out = build_data_source_types(out_data_sources, warnings)
    sqlserver = next(x for x in out["dataSourceTypes"] if x["name"] == "SqlServer")
    csv = next(x for x in out["dataSourceTypes"] if x["name"] == "Csv")

    assert sqlserver["dataTypeMapping"] == [{"sourceType": "nvarchar", "targetType": "string"}]
    assert csv["dataTypeMapping"] == [{"sourceType": "string", "targetType": "string"}]
    assert "Base/DataSourceTypes.json: 'Csv' has no dataTypeMapping; generated fallback mapping." in warnings


def test_build_generator_targets_filters_special_dirs_and_marks_first_default() -> None:
    generated = build_generator_targets(["alpha", ".git", "__cache__", "beta"])
    assert generated == [
        {"name": "alpha", "isDefault": True, "sourcePath": "Generate/alpha", "outputPath": "Output/alpha/generated"},
        {"name": "beta", "isDefault": False, "sourcePath": "Generate/beta", "outputPath": "Output/beta/generated"},
    ]

    fallback = build_generator_targets([])
    assert fallback == [
        {
            "name": "default",
            "isDefault": True,
            "sourcePath": "Generate/default",
            "outputPath": "Output/default/generated",
        }
    ]
