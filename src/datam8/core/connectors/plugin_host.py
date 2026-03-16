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

import importlib
import json
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8NotFoundError,
    Datam8ValidationError,
)
from datam8.core.secrets import resolve_secret_ref

DISABLED_MARKER = ".disabled"
DISTRIBUTION_MARKER = ".distribution.json"


def _capability_template() -> dict[str, Any]:
    return {
        "uiSchema": False,
        "validateConnection": False,
        "metadata": {
            "listTables": False,
            "getTableMetadata": False,
        },
        "runtimeQuery": {
            "sql": False,
            "dataFrame": False,
        },
    }


def _as_bool(value: Any) -> bool:
    return value is True


def _normalize_capabilities(raw: Any, *, connector_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json capabilities must be an object.",
            details={"id": connector_id},
        )

    normalized = _capability_template()
    normalized["uiSchema"] = _as_bool(raw.get("uiSchema"))
    normalized["validateConnection"] = _as_bool(raw.get("validateConnection"))

    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        normalized["metadata"]["listTables"] = _as_bool(metadata.get("listTables"))
        normalized["metadata"]["getTableMetadata"] = _as_bool(metadata.get("getTableMetadata"))

    runtime_query = raw.get("runtimeQuery")
    if isinstance(runtime_query, dict):
        normalized["runtimeQuery"]["sql"] = _as_bool(runtime_query.get("sql"))
        normalized["runtimeQuery"]["dataFrame"] = _as_bool(runtime_query.get("dataFrame"))

    return normalized


def _capability_from_manifest(manifest: Any, path: str) -> bool:
    if not isinstance(manifest, dict):
        return False
    capabilities = manifest.get("capabilities")
    current: Any = capabilities
    for part in path.split("."):
        if not isinstance(current, dict):
            return False
        current = current.get(part)
    return current is True


def _normalize_data_type_mapping(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = (str(item.get("sourceType") or "")).strip()
        target = (str(item.get("targetType") or "")).strip()
        if not source or not target:
            continue
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"sourceType": source, "targetType": target})
    return out


def _connectors_root(plugin_dir: Path) -> Path:
    return plugin_dir / "connectors"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise Datam8ValidationError(message="Invalid JSON.", details={"path": str(path), "error": str(e)}) from e
    if not isinstance(data, dict):
        raise Datam8ValidationError(message="Expected JSON object.", details={"path": str(path)})
    return data


def _read_distribution_metadata(plugin_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    marker = plugin_root / DISTRIBUTION_MARKER
    if not marker.exists():
        return (None, None)

    data = _read_json(marker)
    file_name = data.get("filename")
    sha256 = data.get("sha256")
    install_source = data.get("installSource")
    distribution = {
        "type": "wheel",
        "filename": str(file_name) if isinstance(file_name, str) else "",
        "sha256": str(sha256) if isinstance(sha256, str) else "",
    }
    source = str(install_source) if isinstance(install_source, str) else None
    return (distribution, source)


@dataclass(frozen=True)
class ConnectorPlugin:
    id: str
    display_name: str
    version: str
    manifest_version: int
    entrypoint: str
    capabilities: dict[str, Any]
    data_type_mapping: list[dict[str, str]]
    distribution: dict[str, Any] | None
    install_source: str | None
    root: Path

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "version": self.version,
            "manifestVersion": self.manifest_version,
            "capabilities": self.capabilities,
            "dataTypeMapping": self.data_type_mapping,
            "distribution": self.distribution or {"type": "wheel", "filename": "", "sha256": ""},
            "installSource": self.install_source,
        }


def _parse_plugin_json(*, plugin_root: Path) -> ConnectorPlugin:
    data = _read_json(plugin_root / "plugin.json")
    typ = data.get("pluginType")
    if typ is None:
        typ = data.get("type")
    if typ != "connector":
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json pluginType must be 'connector'.",
            details={"type": typ, "path": str(plugin_root)},
        )

    cid = data.get("id")
    display_name = data.get("displayName")
    version = data.get("version")
    manifest_version = data.get("manifestVersion", 1)
    connector_entrypoint = data.get("connectorEntrypoint")
    entrypoint = connector_entrypoint if isinstance(connector_entrypoint, str) and connector_entrypoint.strip() else data.get("entrypoint")
    capabilities = _normalize_capabilities(data.get("capabilities"), connector_id=str(cid or ""))
    data_type_mapping = _normalize_data_type_mapping(data.get("dataTypeMapping"))

    if not isinstance(cid, str) or not cid.strip():
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json id is required.",
            details={"path": str(plugin_root)},
        )
    if plugin_root.name != cid.strip():
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Plugin folder name must match plugin.json id.",
            details={"expected": plugin_root.name, "actual": cid.strip()},
        )
    if not isinstance(display_name, str) or not display_name.strip():
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json displayName is required.",
            details={"id": cid},
        )
    if not isinstance(version, str) or not version.strip():
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json version is required.",
            details={"id": cid},
        )
    if not isinstance(manifest_version, int) or manifest_version < 1:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="plugin.json manifestVersion must be a positive integer.",
            details={"id": cid},
        )
    if not isinstance(entrypoint, str) or ":" not in entrypoint or not entrypoint.strip():
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Invalid entrypoint (expected 'pkg.module:Class').",
            details={"id": cid, "entrypoint": entrypoint},
        )

    distribution, install_source = _read_distribution_metadata(plugin_root)
    return ConnectorPlugin(
        id=cid.strip(),
        display_name=display_name.strip(),
        version=version.strip(),
        manifest_version=manifest_version,
        entrypoint=entrypoint.strip(),
        capabilities=capabilities,
        data_type_mapping=data_type_mapping,
        distribution=distribution,
        install_source=install_source,
        root=plugin_root,
    )


def is_connector_plugin_enabled(plugin_root: Path) -> bool:
    """Is connector plugin enabled.

    Parameters
    ----------
    plugin_root : Path
        plugin_root parameter value.

    Returns
    -------
    bool
        Computed return value."""
    return not (plugin_root / DISABLED_MARKER).exists()


def parse_connector_plugin(plugin_root: Path) -> ConnectorPlugin:
    """Parse connector plugin.

    Parameters
    ----------
    plugin_root : Path
        plugin_root parameter value.

    Returns
    -------
    ConnectorPlugin
        Computed return value."""
    return _parse_plugin_json(plugin_root=plugin_root)


@contextmanager
def _plugin_sys_path(plugin_root: Path):
    wheel_site_packages = plugin_root / "site-packages"
    src_dir = plugin_root / "src"
    deps_dir = plugin_root / "deps" / "site-packages"
    add_paths: list[str] = []
    if wheel_site_packages.exists():
        add_paths.append(str(wheel_site_packages))
    if deps_dir.exists():
        add_paths.append(str(deps_dir))
    add_paths.append(str(src_dir if src_dir.exists() else plugin_root))
    for add in reversed(add_paths):
        sys.path.insert(0, add)
    try:
        yield
    finally:
        for add in add_paths:
            try:
                sys.path.remove(add)
            except ValueError:
                pass


def _load_connector_class(plugin: ConnectorPlugin) -> type:
    mod_name, attr = plugin.entrypoint.split(":", 1)
    with _plugin_sys_path(plugin.root):
        try:
            module = importlib.import_module(mod_name)
        except Exception as e:
            raise Datam8ExternalSystemError(
                code="plugin_import_failed",
                message="Failed to import connector plugin entrypoint.",
                details={"id": plugin.id, "module": mod_name, "error": str(e)},
            ) from e
        cls = getattr(module, attr, None)
        if cls is None:
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Plugin entrypoint attribute not found.",
                details={"id": plugin.id, "entrypoint": plugin.entrypoint},
            )
        if not isinstance(cls, type):
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Plugin entrypoint must be a class.",
                details={"id": plugin.id, "entrypoint": plugin.entrypoint},
            )
        if not hasattr(cls, "get_manifest"):
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Plugin connector is missing required method.",
                details={"id": plugin.id, "method": "get_manifest"},
            )
        return cls


class _ConnectorClassProxy:
    def __init__(self, *, plugin: ConnectorPlugin, cls: type) -> None:
        self._plugin = plugin
        self._cls = cls

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._cls, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            with _plugin_sys_path(self._plugin.root):
                return attr(*args, **kwargs)

        return _wrapped


def load_connector_class(plugin: ConnectorPlugin) -> Any:
    """Load connector class.

    Parameters
    ----------
    plugin : ConnectorPlugin
        plugin parameter value.

    Returns
    -------
    Any
        Computed return value."""
    cls = _load_connector_class(plugin)
    return _ConnectorClassProxy(plugin=plugin, cls=cls)


def discover_connectors(*, plugin_dir: Path) -> tuple[list[ConnectorPlugin], dict[str, str]]:
    """Discover connectors.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.

    Returns
    -------
    tuple[list[ConnectorPlugin], dict[str, str]]
        Computed return value."""
    root = _connectors_root(plugin_dir)
    if not root.exists():
        return ([], {})
    out: list[ConnectorPlugin] = []
    errors: dict[str, str] = {}
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if not is_connector_plugin_enabled(entry):
            continue
        pid = entry.name
        try:
            out.append(_parse_plugin_json(plugin_root=entry))
        except Exception as e:
            errors[pid] = str(e)
    return (out, errors)


class SecretResolver:
    def __init__(self, *, solution_path: str | None, overrides: dict[str, str] | None = None) -> None:
        self._solution_path = solution_path
        self._overrides = overrides or {}

    def resolve(self, *, key: str, value: str) -> str:
        if key in self._overrides and self._overrides[key].strip():
            return self._overrides[key].strip()
        if not isinstance(value, str):
            return ""
        try:
            return resolve_secret_ref(solution_path=self._solution_path, value=value)
        except Exception as e:
            raise Datam8ValidationError(
                code="connector_secret_resolution_failed",
                message="Secret reference could not be resolved.",
                details={"key": key, "error": str(e)},
            ) from e


def _to_string_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if v is None:
            continue
        out[k] = v if isinstance(v, str) else str(v)
    return out


def _secret_keys_from_ui_schema(schema: dict[str, Any]) -> set[str]:
    secret_keys: set[str] = set()
    auth_modes = schema.get("authModes")
    if not isinstance(auth_modes, list):
        return secret_keys
    for m in auth_modes:
        if not isinstance(m, dict):
            continue
        fields = m.get("fields")
        if not isinstance(fields, list):
            continue
        for f in fields:
            if not isinstance(f, dict):
                continue
            if f.get("secret") is True or f.get("type") == "secret":
                key = f.get("key")
                if isinstance(key, str) and key.strip():
                    secret_keys.add(key.strip())
    return secret_keys


def _validate_no_plaintext_secrets(*, schema: dict[str, Any], extended_properties: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    secret_keys = _secret_keys_from_ui_schema(schema)
    for key in sorted(secret_keys):
        v = (extended_properties.get(key) or "").strip()
        if not v:
            continue
        if not v.lower().startswith("secretref://"):
            errors.append(
                {
                    "key": key,
                    "message": "Do not store plaintext secrets in extendedProperties. Store a secretRef://... reference instead.",
                    "level": "error",
                }
            )
    return errors


def has_capability(manifest_or_plugin: Any, capability_path: str) -> bool:
    if isinstance(manifest_or_plugin, ConnectorPlugin):
        return _capability_from_manifest({"capabilities": manifest_or_plugin.capabilities}, capability_path)
    if isinstance(manifest_or_plugin, dict):
        return _capability_from_manifest(manifest_or_plugin, capability_path)
    return False


def require_capability(manifest_or_plugin: Any, capability_path: str) -> None:
    if has_capability(manifest_or_plugin, capability_path):
        return

    connector_id: str | None = None
    if isinstance(manifest_or_plugin, ConnectorPlugin):
        connector_id = manifest_or_plugin.id
    elif isinstance(manifest_or_plugin, dict):
        raw = manifest_or_plugin.get("id")
        if isinstance(raw, str):
            connector_id = raw

    raise Datam8ValidationError(
        code="connector_capability_missing",
        message=f"Connector does not support capability '{capability_path}'.",
        details={"id": connector_id, "capability": capability_path},
    )


def get_connectors_state(*, plugin_dir: Path) -> dict[str, Any]:
    """Get connectors state.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value."""
    connectors, errors = discover_connectors(plugin_dir=plugin_dir)
    return {"pluginDir": str(plugin_dir), "connectors": [c.to_summary() for c in connectors], "errors": errors}


def get_connector(*, plugin_dir: Path, connector_id: str) -> ConnectorPlugin:
    """Get connector.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.
    connector_id : str
        connector_id parameter value.

    Returns
    -------
    ConnectorPlugin
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails."""
    connectors, _errors = discover_connectors(plugin_dir=plugin_dir)
    needle = (connector_id or "").strip().lower()
    for c in connectors:
        if c.id.strip().lower() == needle:
            return c
    raise Datam8NotFoundError(message="Connector not found.", details={"id": connector_id})


def load_ui_schema(*, plugin: ConnectorPlugin) -> dict[str, Any]:
    """Load ui schema.

    Parameters
    ----------
    plugin : ConnectorPlugin
        plugin parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value.

    Raises
    ------
    Datam8ValidationError
        Raised when validation or runtime execution fails."""
    require_capability(plugin, "uiSchema")
    cls = load_connector_class(plugin)
    if not hasattr(cls, "get_ui_schema"):
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector advertises uiSchema but get_ui_schema is missing.",
            details={"id": plugin.id},
        )
    schema = cls.get_ui_schema()  # type: ignore[attr-defined]
    if not isinstance(schema, dict):
        raise Datam8ValidationError(message="Connector ui schema must be an object.", details={"id": plugin.id})
    return schema


def validate_connection(
    *,
    plugin: ConnectorPlugin,
    solution_path: str | None,
    extended_properties: Any,
    runtime_secret_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate connection.

    Parameters
    ----------
    plugin : ConnectorPlugin
        plugin parameter value.
    solution_path : str | None
        solution_path parameter value.
    extended_properties : Any
        extended_properties parameter value.
    runtime_secret_overrides : dict[str, str] | None
        runtime_secret_overrides parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value.

    Raises
    ------
    Datam8ExternalSystemError
        Raised when validation or runtime execution fails."""
    require_capability(plugin, "validateConnection")
    cls = load_connector_class(plugin)
    if not hasattr(cls, "validate_connection"):
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector advertises validateConnection but validate_connection is missing.",
            details={"id": plugin.id},
        )

    props = _to_string_map(extended_properties)
    schema: dict[str, Any] = {}
    if has_capability(plugin, "uiSchema") and hasattr(cls, "get_ui_schema"):
        raw_schema = cls.get_ui_schema()  # type: ignore[attr-defined]
        if not isinstance(raw_schema, dict):
            raise Datam8ValidationError(message="Connector ui schema must be an object.", details={"id": plugin.id})
        schema = raw_schema
    errors: list[dict[str, str]] = []
    if schema:
        errors.extend(_validate_no_plaintext_secrets(schema=schema, extended_properties=props))

    resolver = SecretResolver(solution_path=solution_path, overrides=runtime_secret_overrides or {})
    resolved_props: dict[str, str] = {}
    for k, v in props.items():
        if isinstance(v, str) and v.lower().startswith("secretref://"):
            try:
                resolved_props[k] = resolver.resolve(key=k, value=v)
            except Exception:
                resolved_props[k] = ""
                errors.append({"key": k, "message": "Secret reference could not be resolved.", "level": "error"})
        else:
            resolved_props[k] = v

    try:
        plugin_errors = cls.validate_connection(resolved_props, resolver)  # type: ignore[attr-defined]
    except Exception as e:
        raise Datam8ExternalSystemError(
            code="connector_validate_failed",
            message="Connector validation failed.",
            details={"id": plugin.id, "error": str(e)},
        ) from e

    if isinstance(plugin_errors, list):
        for e in plugin_errors:
            if not isinstance(e, dict):
                continue
            key = e.get("key")
            msg = e.get("message")
            lvl = e.get("level") or "error"
            if isinstance(key, str) and isinstance(msg, str):
                errors.append({"key": key, "message": msg, "level": str(lvl)})

    ok = not any((e.get("level") or "error") == "error" for e in errors)
    return {"ok": ok, "errors": errors}


def _call(
    *,
    plugin: ConnectorPlugin,
    fn: Callable[[type, dict[str, str], SecretResolver], Any],
    solution_path: str | None,
    extended_properties: dict[str, str],
    runtime_secret_overrides: dict[str, str] | None = None,
) -> Any:
    cls = load_connector_class(plugin)
    resolver = SecretResolver(solution_path=solution_path, overrides=runtime_secret_overrides or {})
    return fn(cls, extended_properties, resolver)
