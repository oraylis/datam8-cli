from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from datam8.core.connectors.types import ConnectorModule


def _norm(value: str) -> str:
    return (value or "").strip().lower()


@dataclass(frozen=True)
class ConnectorSource:
    kind: str
    pluginId: Optional[str] = None
    entryPath: Optional[str] = None


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors_by_id: dict[str, tuple[ConnectorModule, ConnectorSource]] = {}
        self._connector_id_by_alias: dict[str, str] = {}

    def register(self, module: ConnectorModule, source: ConnectorSource) -> None:
        manifest = module.manifest or {}
        name = manifest.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Connector manifest.name is required")
        cid = _norm(name)
        self._connectors_by_id[cid] = (module, source)
        aliases = manifest.get("aliases") or []
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str) and _norm(a):
                    self._connector_id_by_alias[_norm(a)] = cid

    def unregister_all_plugins(self) -> None:
        for cid, (_m, src) in list(self._connectors_by_id.items()):
            if src.kind == "plugin":
                del self._connectors_by_id[cid]
        for alias, cid in list(self._connector_id_by_alias.items()):
            m = self._connectors_by_id.get(cid)
            if not m:
                del self._connector_id_by_alias[alias]
                continue
            if m[1].kind == "plugin":
                del self._connector_id_by_alias[alias]

    def list(self) -> list[dict[str, Any]]:
        out = []
        for module, source in self._connectors_by_id.values():
            out.append({"manifest": module.manifest, "source": source.__dict__})
        return out

    def resolve_by_id(self, id: str) -> Optional[ConnectorModule]:
        v = self._connectors_by_id.get(_norm(id))
        return v[0] if v else None

    def resolve_by_alias(self, alias: str) -> Optional[ConnectorModule]:
        cid = self._connector_id_by_alias.get(_norm(alias))
        if not cid:
            return None
        return self._connectors_by_id.get(cid, (None, None))[0]  # type: ignore[return-value]


connector_registry = ConnectorRegistry()

