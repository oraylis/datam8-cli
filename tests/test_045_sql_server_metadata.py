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

from types import SimpleNamespace

import polars as pl
import pytest

from datam8.plugins.builtins.sql_server import SqlServer
from datam8_model.data_source import SourceField, SourceObject


def _make_plugin() -> SqlServer:
    plugin = SqlServer.__new__(SqlServer)
    plugin._data_source = SimpleNamespace(name="AdventureWorks")
    return plugin


def test_sql_server_get_table_metadata_maps_information_schema_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _make_plugin()

    raw = pl.DataFrame(
        [
            {
                "COLUMN_NAME": "ProductID",
                "ORDINAL_POSITION": 1,
                "DATA_TYPE": "int",
                "CHARACTER_MAXIMUM_LENGTH": None,
                "NUMERIC_PRECISION": 10,
                "NUMERIC_SCALE": 0,
                "IS_NULLABLE": "NO",
                "IS_PRIMARY_KEY": 1,
            },
            {
                "COLUMN_NAME": "Name",
                "ORDINAL_POSITION": 2,
                "DATA_TYPE": "nvarchar",
                "CHARACTER_MAXIMUM_LENGTH": 100,
                "NUMERIC_PRECISION": None,
                "NUMERIC_SCALE": None,
                "IS_NULLABLE": "YES",
                "IS_PRIMARY_KEY": 0,
            },
        ]
    )

    monkeypatch.setattr(plugin, "_execute_query", lambda _query: raw)

    metadata = plugin.get_table_metadata("Product", "dbo")
    rows = metadata.to_dicts()

    assert len(rows) == 2
    assert rows[0]["name"] == "ProductID"
    assert rows[0]["ordinal"] == 1
    assert rows[0]["dataType"] == "int"
    assert rows[0]["isNullable"] is False
    assert rows[0]["isPrimaryKey"] is True
    assert rows[1]["name"] == "Name"
    assert rows[1]["isNullable"] is True
    assert rows[1]["isPrimaryKey"] is False

    # must pass route-level SourceField validation used in /sources/* endpoints
    for row in rows:
        SourceField.from_dict(row)


def test_sql_server_get_table_metadata_raises_for_missing_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _make_plugin()
    raw = pl.DataFrame([{"COLUMN_NAME": "ProductID"}])
    monkeypatch.setattr(plugin, "_execute_query", lambda _query: raw)

    with pytest.raises(Exception, match="Invalid source metadata row"):
        plugin.get_table_metadata("Product", "dbo")


def test_source_models_allow_optional_description_and_properties() -> None:
    table = SourceObject.from_dict(
        {
            "schema": "contract-a",
            "name": "customers",
            "type": "object",
            "description": "Customer master entity",
            "properties": [{"property": "classification", "value": "restricted"}],
            "sourceOverride": {
                "dataSource": "crm_api",
                "sourceLocation": "/customers",
            },
        }
    )
    assert table.description == "Customer master entity"
    assert table.properties is not None
    assert table.properties[0].property == "classification"
    assert table.properties[0].value == "restricted"
    assert table.sourceOverride is not None
    assert table.sourceOverride.dataSource == "crm_api"
    assert table.sourceOverride.sourceLocation == "/customers"
    assert table.to_dict()["sourceOverride"] == {
        "dataSource": "crm_api",
        "sourceLocation": "/customers",
    }

    column = SourceField.from_dict(
        {
            "name": "customer_id",
            "ordinal": 1,
            "dataType": "string",
            "isNullable": False,
            "isPrimaryKey": True,
            "description": "Technical customer key",
            "properties": [{"property": "classification", "value": "restricted"}],
            "relationships": [
                {
                    "dataSource": "edwh-drillisch-prod",
                    "targetLocation": "[dm_dom_contract].[contract_instance]",
                    "sourceName": "customer_id",
                    "targetName": "subscriber_id",
                }
            ],
        }
    )
    assert column.description == "Technical customer key"
    assert column.properties is not None
    assert column.properties[0].property == "classification"
    assert column.properties[0].value == "restricted"
    assert column.relationships is not None
    assert column.relationships[0]["targetName"] == "subscriber_id"
