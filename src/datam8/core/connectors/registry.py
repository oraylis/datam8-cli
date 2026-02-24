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

from dataclasses import asdict, dataclass
from typing import Any

from datam8.core.connectors.types import ConnectorModule


def _norm(value: str) -> str:
    return (value or "").strip().lower()


@dataclass(frozen=True)
class ConnectorSource:
    kind: str
    pluginId: str | None = None
    entryPath: str | None = None


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
            out.append({"manifest": module.manifest, "source": asdict(source)})
        return out

    def resolve_by_id(self, id: str) -> ConnectorModule | None:
        v = self._connectors_by_id.get(_norm(id))
        return v[0] if v else None

    def resolve_by_alias(self, alias: str) -> ConnectorModule | None:
        cid = self._connector_id_by_alias.get(_norm(alias))
        if not cid:
            return None
        return self._connectors_by_id.get(cid, (None, None))[0]  # type: ignore[return-value]


connector_registry = ConnectorRegistry()

