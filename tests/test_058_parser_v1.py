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

import pytest

from datam8.core import parser_v1


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_parse_base_attribute_types_uses_typed_model(tmp_path: Path) -> None:
    file_path = tmp_path / "AttributeTypes.json"
    _write_json(
        file_path,
        {
            "type": "attributeType",
            "items": [
                {
                    "name": "Val",
                    "displayName": "Value",
                    "defaultType": "double",
                    "hasUnit": "UnitFree",
                    "isUnit": "NoUnit",
                    "canBeInRelation": "false",
                    "isDefaultProperty": 0,
                }
            ],
            "legacyFieldToDrop": True,
        },
    )

    parsed = parser_v1.parse_base_file(file_path, "AttributeTypes.json")
    payload = parsed.model_dump(exclude_none=True)

    assert payload["items"][0]["name"] == "Val"
    assert payload["items"][0]["hasUnit"] == "UnitFree"
    assert "legacyFieldToDrop" not in payload


def test_parse_model_file_rejects_unknown_type(tmp_path: Path) -> None:
    file_path = tmp_path / "Unknown.json"
    _write_json(file_path, {"type": "unknown", "entity": {}})

    with pytest.raises(parser_v1.V1ParseError):
        parser_v1.parse_model_file(file_path)
