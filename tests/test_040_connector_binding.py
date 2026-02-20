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

import pytest
from pytest_cases import parametrize_with_cases
from test_040_connector_binding_cases import (
    CasesConnectorBindingDecode,
    CasesConnectorBindingEncode,
)

from datam8.core.connectors.binding import (
    decode_connector_binding,
    encode_connector_binding,
)
from datam8.core.errors import Datam8ValidationError
from datam8_model import data_source as data_source_model


@parametrize_with_cases(
    "case_data",
    cases=CasesConnectorBindingDecode,
    glob="*_valid",
)
def test_decode_binding_valid(case_data) -> None:
    connection_properties, expected_id, expected_version = case_data
    binding = decode_connector_binding(connection_properties)
    if expected_id is None:
        assert binding is None
        return

    assert binding is not None
    assert binding.connector_id == expected_id
    assert binding.connector_version == expected_version


@parametrize_with_cases(
    "connection_properties",
    cases=CasesConnectorBindingDecode,
    glob="*_invalid",
)
def test_decode_binding_invalid(connection_properties) -> None:
    with pytest.raises(Datam8ValidationError):
        decode_connector_binding(connection_properties)


@parametrize_with_cases(
    "case_data",
    cases=CasesConnectorBindingEncode,
)
def test_encode_overwrites_reserved_entries_preserving_others(case_data) -> None:
    connection_properties, connector_id, connector_version, expected_names = case_data
    out = encode_connector_binding(
        connection_properties=connection_properties,
        connector_id=connector_id,
        connector_version=connector_version,
    )
    names = {p["name"] for p in out}
    assert expected_names.issubset(names)
    assert "__connector.id=old" not in names


def test_decode_binding_accepts_model_connection_properties() -> None:
    connection_properties = [
        data_source_model.ConnectionProperty(
            name="__connector.id=sqlserver",
            required=True,
            description="Reserved: connector binding (do not render).",
        ),
        data_source_model.ConnectionProperty(
            name="__connector.version=0.1.0",
            required=False,
            description="Reserved: connector version (do not render).",
        ),
    ]
    binding = decode_connector_binding(connection_properties)
    assert binding is not None
    assert binding.connector_id == "sqlserver"
    assert binding.connector_version == "0.1.0"
