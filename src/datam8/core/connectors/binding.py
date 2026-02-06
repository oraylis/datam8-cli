from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datam8.core.errors import Datam8ValidationError

CONNECTOR_ID_PREFIX = "__connector.id="
CONNECTOR_VERSION_PREFIX = "__connector.version="


@dataclass(frozen=True)
class ConnectorBinding:
    connector_id: str
    version_req: str | None = None


def is_reserved_connection_property(name: str) -> bool:
    n = (name or "").strip()
    return n.startswith(CONNECTOR_ID_PREFIX) or n.startswith(CONNECTOR_VERSION_PREFIX)


def decode_connector_binding(connection_properties: Any) -> ConnectorBinding | None:
    """
    Variant A encoding stored in DataSourceType.connectionProperties:
      - "__connector.id=<connectorId>" (required exactly once when bound)
      - "__connector.version=<semver or range>" (optional at most once)
    """
    props = connection_properties if isinstance(connection_properties, list) else []
    connector_ids: list[str] = []
    version_reqs: list[str] = []

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
            version_reqs.append(n[len(CONNECTOR_VERSION_PREFIX) :].strip())

    connector_ids = [c for c in connector_ids if c]
    version_reqs = [v for v in version_reqs if v]

    if not connector_ids and not version_reqs:
        return None
    if len(connector_ids) != 1:
        raise Datam8ValidationError(
            message="Invalid connector binding: expected exactly one __connector.id entry.",
            details={"connectorIds": connector_ids, "count": len(connector_ids)},
        )
    if len(version_reqs) > 1:
        raise Datam8ValidationError(
            message="Invalid connector binding: expected at most one __connector.version entry.",
            details={"versionReqs": version_reqs, "count": len(version_reqs)},
        )
    return ConnectorBinding(connector_id=connector_ids[0], version_req=version_reqs[0] if version_reqs else None)


def encode_connector_binding(
    *,
    connection_properties: Any,
    connector_id: str,
    version_req: str | None = None,
) -> list[dict[str, Any]]:
    cid = (connector_id or "").strip()
    if not cid:
        raise Datam8ValidationError(message="connector_id is required.", details=None)
    vr = (version_req or "").strip() or None

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
    if vr:
        kept.append({"name": f"{CONNECTOR_VERSION_PREFIX}{vr}", "required": False, "description": "Reserved: connector version requirement (do not render)."})
    return kept

