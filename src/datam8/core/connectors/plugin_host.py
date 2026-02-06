from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from datam8.core.errors import Datam8ExternalSystemError, Datam8NotFoundError, Datam8ValidationError
from datam8.core.secrets import resolve_secret_ref

DISABLED_MARKER = ".disabled"


@dataclass(frozen=True)
class ConnectorPlugin:
    id: str
    display_name: str
    version: str
    entrypoint: str
    capabilities: list[str]
    root: Path

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "version": self.version,
            "capabilities": list(self.capabilities),
        }


def _connectors_root(plugin_dir: Path) -> Path:
    return plugin_dir / "connectors"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise Datam8ValidationError(message="Invalid JSON.", details={"path": str(path), "error": str(e)})
    if not isinstance(data, dict):
        raise Datam8ValidationError(message="Expected JSON object.", details={"path": str(path)})
    return data


def _parse_plugin_json(*, plugin_root: Path) -> ConnectorPlugin:
    data = _read_json(plugin_root / "plugin.json")
    typ = data.get("pluginType")
    if typ is None:
        # Backwards-friendly: accept legacy `type` when provided.
        typ = data.get("type")
    if typ != "connector":
        raise Datam8ValidationError(message="plugin.json pluginType must be 'connector'.", details={"type": typ, "path": str(plugin_root)})

    cid = data.get("id")
    display_name = data.get("displayName")
    version = data.get("version")
    connector_entrypoint = data.get("connectorEntrypoint")
    entrypoint = connector_entrypoint if isinstance(connector_entrypoint, str) and connector_entrypoint.strip() else data.get("entrypoint")
    capabilities = data.get("capabilities")

    if not isinstance(cid, str) or not cid.strip():
        raise Datam8ValidationError(message="plugin.json id is required.", details={"path": str(plugin_root)})
    if plugin_root.name != cid.strip():
        raise Datam8ValidationError(message="Plugin folder name must match plugin.json id.", details={"expected": plugin_root.name, "actual": cid.strip()})
    if not isinstance(display_name, str) or not display_name.strip():
        raise Datam8ValidationError(message="plugin.json displayName is required.", details={"id": cid})
    if not isinstance(version, str) or not version.strip():
        raise Datam8ValidationError(message="plugin.json version is required.", details={"id": cid})
    if not isinstance(entrypoint, str) or ":" not in entrypoint or not entrypoint.strip():
        raise Datam8ValidationError(message="Invalid entrypoint (expected 'pkg.module:Class').", details={"id": cid, "entrypoint": entrypoint})
    if not isinstance(capabilities, list) or not all(isinstance(x, str) and x.strip() for x in capabilities):
        raise Datam8ValidationError(message="plugin.json capabilities must be a list of strings.", details={"id": cid})

    return ConnectorPlugin(
        id=cid.strip(),
        display_name=display_name.strip(),
        version=version.strip(),
        entrypoint=entrypoint.strip(),
        capabilities=[x.strip() for x in capabilities],
        root=plugin_root,
    )


def is_connector_plugin_enabled(plugin_root: Path) -> bool:
    return not (plugin_root / DISABLED_MARKER).exists()


def parse_connector_plugin(plugin_root: Path) -> ConnectorPlugin:
    return _parse_plugin_json(plugin_root=plugin_root)


@contextmanager
def _plugin_sys_path(plugin_root: Path):
    src_dir = plugin_root / "src"
    deps_dir = plugin_root / "deps" / "site-packages"
    add_paths: list[str] = []
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
            )
        cls = getattr(module, attr, None)
        if cls is None:
            raise Datam8ValidationError(message="Plugin entrypoint attribute not found.", details={"id": plugin.id, "entrypoint": plugin.entrypoint})
        if not isinstance(cls, type):
            raise Datam8ValidationError(message="Plugin entrypoint must be a class.", details={"id": plugin.id, "entrypoint": plugin.entrypoint})
        for m in (
            "get_manifest",
            "get_ui_schema",
            "validate_connection",
            "test_connection",
            "list_schemas",
            "list_tables",
            "get_table_metadata",
        ):
            if not hasattr(cls, m):
                raise Datam8ValidationError(message="Plugin connector is missing required method.", details={"id": plugin.id, "method": m})
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
    cls = _load_connector_class(plugin)
    return _ConnectorClassProxy(plugin=plugin, cls=cls)


def discover_connectors(*, plugin_dir: Path) -> tuple[list[ConnectorPlugin], dict[str, str]]:
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
        return resolve_secret_ref(solution_path=self._solution_path, value=value) if isinstance(value, str) else ""


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


def get_connectors_state(*, plugin_dir: Path) -> dict[str, Any]:
    connectors, errors = discover_connectors(plugin_dir=plugin_dir)
    return {"pluginDir": str(plugin_dir), "connectors": [c.to_summary() for c in connectors], "errors": errors}


def get_connector(*, plugin_dir: Path, connector_id: str) -> ConnectorPlugin:
    connectors, _errors = discover_connectors(plugin_dir=plugin_dir)
    needle = (connector_id or "").strip().lower()
    for c in connectors:
        if c.id.strip().lower() == needle:
            return c
    raise Datam8NotFoundError(message="Connector not found.", details={"id": connector_id})


def load_ui_schema(*, plugin: ConnectorPlugin) -> dict[str, Any]:
    cls = load_connector_class(plugin)
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
    cls = load_connector_class(plugin)
    props = _to_string_map(extended_properties)
    schema = load_ui_schema(plugin=plugin)
    errors: list[dict[str, str]] = []
    errors.extend(_validate_no_plaintext_secrets(schema=schema, extended_properties=props))

    resolver = SecretResolver(solution_path=solution_path, overrides=runtime_secret_overrides or {})
    # Backend-resolved props for validation (contract).
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
        raise Datam8ExternalSystemError(code="connector_validate_failed", message="Connector validation failed.", details={"id": plugin.id, "error": str(e)})

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
