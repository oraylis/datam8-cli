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

import asyncio
import json
from pathlib import Path

import pytest

from datam8 import config as datam8_config
from datam8 import parser, parser_exceptions


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _create_solution(tmp_path: Path, folder_payload: dict) -> Path:
    base = tmp_path / "Base"
    model = tmp_path / "Model" / "010-Stage" / "Sales"

    _write_json(
        base / "DataProducts.json",
        {
            "type": "dataProducts",
            "dataProducts": [
                {
                    "name": "Sales",
                    "dataModules": [{"name": "Customer"}],
                }
            ],
        },
    )
    _write_json(
        model / "Customer.json",
        {
            "id": 1,
            "name": "Customer",
            "attributes": [
                {
                    "ordinalNumber": 1,
                    "name": "CustomerId",
                    "attributeType": "ID",
                    "dataType": {"type": "int", "nullable": False},
                    "dateAdded": "2026-01-01T00:00:00Z",
                }
            ],
            "sources": [],
            "relationships": [],
            "transformations": [],
        },
    )
    _write_json(model / ".properties.json", folder_payload)
    _write_json(
        tmp_path / "TestSolution.dm8s",
        {
            "schemaVersion": "2.0.0",
            "basePath": "Base",
            "modelPath": "Model",
            "generatorTargets": [
                {
                    "name": "dummy",
                    "isDefault": True,
                    "sourcePath": "Generate/dummy",
                    "outputPath": "Output/dummy/generated",
                }
            ],
        },
    )
    return tmp_path / "TestSolution.dm8s"


def test_folder_validation_accepts_existing_product_module(tmp_path: Path) -> None:
    solution_path = _create_solution(
        tmp_path,
        {
            "type": "folders",
            "folders": [
                {
                    "id": 101,
                    "name": "Sales",
                    "dataProduct": "Sales",
                    "dataModule": "Customer",
                    "properties": [],
                }
            ],
        },
    )

    datam8_config.solution_folder_path = solution_path.parent
    model = asyncio.run(parser.parse_full_solution_async(solution_path))
    assert model is not None


def test_folder_validation_rejects_invalid_module_without_product(tmp_path: Path) -> None:
    solution_path = _create_solution(
        tmp_path,
        {
            "type": "folders",
            "folders": [
                {
                    "id": 101,
                    "name": "Sales",
                    "dataModule": "Customer",
                    "properties": [],
                }
            ],
        },
    )

    datam8_config.solution_folder_path = solution_path.parent
    with pytest.raises(parser_exceptions.ModelParseException) as exc_info:
        asyncio.run(parser.parse_full_solution_async(solution_path))

    assert "dataModule 'Customer' requires dataProduct" in str(exc_info.value)
