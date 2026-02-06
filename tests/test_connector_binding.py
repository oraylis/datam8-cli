from __future__ import annotations

import pytest

from datam8.core.connectors.binding import decode_connector_binding, encode_connector_binding
from datam8.core.errors import Datam8ValidationError


def test_decode_none_when_unbound() -> None:
    assert decode_connector_binding(None) is None
    assert decode_connector_binding([]) is None
    assert decode_connector_binding([{"name": "host", "required": True}]) is None


def test_decode_id_only() -> None:
    b = decode_connector_binding([{"name": "__connector.id=postgresql", "required": True}])
    assert b is not None
    assert b.connector_id == "postgresql"
    assert b.version_req is None


def test_decode_id_and_version() -> None:
    b = decode_connector_binding(
        [
            {"name": "__connector.id=sqlserver", "required": True},
            {"name": "__connector.version=^0.1.0", "required": False},
        ]
    )
    assert b is not None
    assert b.connector_id == "sqlserver"
    assert b.version_req == "^0.1.0"


def test_decode_rejects_multiple_ids() -> None:
    with pytest.raises(Datam8ValidationError):
        decode_connector_binding(
            [
                {"name": "__connector.id=a", "required": True},
                {"name": "__connector.id=b", "required": True},
            ]
        )


def test_decode_rejects_multiple_versions() -> None:
    with pytest.raises(Datam8ValidationError):
        decode_connector_binding(
            [
                {"name": "__connector.id=a", "required": True},
                {"name": "__connector.version=1.0.0", "required": False},
                {"name": "__connector.version=2.0.0", "required": False},
            ]
        )


def test_encode_overwrites_reserved_entries_preserving_others() -> None:
    out = encode_connector_binding(
        connection_properties=[
            {"name": "host", "required": True},
            {"name": "__connector.id=old", "required": True},
            {"name": "__connector.version=>=0.1.0", "required": False},
        ],
        connector_id="new",
        version_req="0.2.0",
    )
    names = [p["name"] for p in out]
    assert "host" in names
    assert "__connector.id=new" in names
    assert "__connector.version=0.2.0" in names
    assert "__connector.id=old" not in names

