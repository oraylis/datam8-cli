from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datam8.core.errors import Datam8ValidationError

CONNECTOR_ID_PREFIX = "__connector.id="
CONNECTOR_VERSION_PREFIX = "__connector.version="


@dataclass(frozen=True)
class ConnectorBinding:
    connector_id: str
    connector_version: str | None = None


def is_reserved_connection_property(name: str) -> bool:
    n = (name or "").strip()
    return n.startswith(CONNECTOR_ID_PREFIX) or n.startswith(CONNECTOR_VERSION_PREFIX)


def decode_connector_binding(connection_properties: Any) -> ConnectorBinding | None:
    """
    Variant A encoding stored in DataSourceType.connectionProperties:
      - "__connector.id=<connectorId>" (required exactly once when bound)
      - "__connector.version=<connectorVersion>" (optional at most once)
    """
    props = connection_properties if isinstance(connection_properties, list) else []
    connector_ids: list[str] = []
    connector_versions: list[str] = []

    for p in props:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        n = name.strip()
        if n.startswith(CONNECTOR_ID_PREFIX):
            connector_ids.append(n[len(CONNECTOR_ID_PREFIX) :].strip())
        elif n.startswith(CONNECTOR_VERSION_PREFIX):
            connector_versions.append(n[len(CONNECTOR_VERSION_PREFIX) :].strip())

    connector_ids = [c for c in connector_ids if c]
    connector_versions = [v for v in connector_versions if v]

    if not connector_ids and not connector_versions:
        return None
    if len(connector_ids) != 1:
        raise Datam8ValidationError(
            message="Invalid connector binding: expected exactly one __connector.id entry.",
            details={"connectorIds": connector_ids, "count": len(connector_ids)},
        )
    if len(connector_versions) > 1:
        raise Datam8ValidationError(
            message="Invalid connector binding: expected at most one __connector.version entry.",
            details={"connectorVersions": connector_versions, "count": len(connector_versions)},
        )
    return ConnectorBinding(
        connector_id=connector_ids[0],
        connector_version=connector_versions[0] if connector_versions else None,
    )


def encode_connector_binding(
    *,
    connection_properties: Any,
    connector_id: str,
    connector_version: str | None = None,
) -> list[dict[str, Any]]:
    cid = (connector_id or "").strip()
    if not cid:
        raise Datam8ValidationError(message="connector_id is required.", details=None)
    version = (connector_version or "").strip() or None

    base = connection_properties if isinstance(connection_properties, list) else []
    kept: list[dict[str, Any]] = []
    for p in base:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if isinstance(name, str) and is_reserved_connection_property(name):
            continue
        kept.append(p)

    kept.append({"name": f"{CONNECTOR_ID_PREFIX}{cid}", "required": True, "description": "Reserved: connector binding (do not render)."})
    if version:
        kept.append({"name": f"{CONNECTOR_VERSION_PREFIX}{version}", "required": False, "description": "Reserved: connector version (do not render)."})
    return kept
