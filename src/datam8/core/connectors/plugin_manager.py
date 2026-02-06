from __future__ import annotations

import io
import json
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from datam8.core.connectors.plugin_host import (
    get_connectors_state,
    load_connector_class,
    parse_connector_plugin,
)
from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError

DISABLED_MARKER = ".disabled"


@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    display_name: str
    version: str


def default_plugin_dir() -> Path:
    base = Path(user_data_dir(appname="datam8", appauthor=False))
    plugin_dir = base / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return plugin_dir


def _connectors_root(plugin_dir: Path) -> Path:
    root = plugin_dir / "connectors"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _disabled_marker(plugin_root: Path) -> Path:
    return plugin_root / DISABLED_MARKER


def _is_enabled(plugin_root: Path) -> bool:
    return not _disabled_marker(plugin_root).exists()


def _safe_relpath(dest: Path, zip_name: str) -> Path:
    name = (zip_name or "").replace("\\", "/")
    if not name or name.startswith("/") or name.startswith("\\"):
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    parts = [p for p in name.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    rel = Path(*parts)
    target = (dest / rel).resolve()
    base = dest.resolve()
    if target == base or base not in target.parents:
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    return rel


def _extract_zip_to_tmp(zip_bytes: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
        for info in archive.infolist():
            rel = _safe_relpath(dest, info.filename)
            target = dest / rel
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _read_plugin_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise Datam8ValidationError(message="Invalid JSON.", details={"path": str(path), "error": str(e)})
    if not isinstance(data, dict):
        raise Datam8ValidationError(message="Expected JSON object.", details={"path": str(path)})
    return data


def _parse_manifest(path: Path) -> tuple[str, str, str]:
    data = _read_plugin_json(path)
    typ = data.get("pluginType")
    if typ is None:
        typ = data.get("type")
    if typ != "connector":
        raise Datam8ValidationError(message="plugin.json pluginType must be 'connector'.", details={"path": str(path)})
    cid = data.get("id")
    display = data.get("displayName")
    version = data.get("version")
    if not isinstance(cid, str) or not cid.strip():
        raise Datam8ValidationError(message="plugin.json id is required.", details={"path": str(path)})
    if not isinstance(display, str) or not display.strip():
        raise Datam8ValidationError(message="plugin.json displayName is required.", details={"path": str(path)})
    if not isinstance(version, str) or not version.strip():
        raise Datam8ValidationError(message="plugin.json version is required.", details={"path": str(path)})
    return (cid.strip(), display.strip(), version.strip())


def verify_zip_bundle(*, zip_bytes: bytes) -> PluginDescriptor:
    with tempfile.TemporaryDirectory(prefix="datam8-connector-plugin-verify-") as td:
        temp_root = Path(td)
        _extract_zip_to_tmp(zip_bytes, temp_root)
        roots = _find_plugin_roots(temp_root)
        if not roots:
            raise Datam8ValidationError(message="No connector plugin root found in ZIP.", details=None)
        if len(roots) > 1:
            raise Datam8ValidationError(message="ZIP must contain exactly one connector plugin.", details={"roots": [str(r.name) for r in roots]})
        plugin_json = roots[0] / "plugin.json"
        cid, display, version = _parse_manifest(plugin_json)
        return PluginDescriptor(id=cid, display_name=display, version=version)


def _find_plugin_roots(extracted_root: Path) -> list[Path]:
    roots: list[Path] = []
    if (extracted_root / "plugin.json").exists():
        roots.append(extracted_root)
    for entry in sorted(extracted_root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if (entry / "plugin.json").exists():
            roots.append(entry)
    unique: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        key = str(r.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def list_plugins(plugin_dir: Path) -> dict[str, Any]:
    root = _connectors_root(plugin_dir)
    plugins: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for folder in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir():
            continue
        plugin_json = folder / "plugin.json"
        enabled = _is_enabled(folder)
        item: dict[str, Any] = {
            "id": folder.name,
            "enabled": enabled,
            "entry": f"connectors/{folder.name}/plugin.json",
        }

        if not plugin_json.exists():
            errors[folder.name] = "Missing plugin.json."
            plugins.append(item)
            continue

        try:
            cid, display, version = _parse_manifest(plugin_json)
            item["id"] = cid
            item["name"] = display
            item["displayName"] = display
            item["version"] = version
            if cid != folder.name:
                errors[cid] = f"Plugin folder name '{folder.name}' does not match plugin id '{cid}'."
            else:
                parsed = parse_connector_plugin(folder)
                item["capabilities"] = list(parsed.capabilities)
                if enabled:
                    load_connector_class(parsed)
        except Exception as e:
            errors[item["id"]] = str(e)
        plugins.append(item)

    plugins.sort(key=lambda p: str(p.get("id", "")).lower())
    return {"pluginDir": str(plugin_dir), "plugins": plugins, "errors": errors}


def reload(plugin_dir: Path) -> dict[str, Any]:
    return list_plugins(plugin_dir)


def install_zip(*, plugin_dir: Path, zip_bytes: bytes, file_name: str | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="datam8-connector-plugin-") as td:
        temp_root = Path(td)
        _extract_zip_to_tmp(zip_bytes, temp_root)
        roots = _find_plugin_roots(temp_root)
        if not roots:
            raise Datam8ValidationError(message="No connector plugin root found in ZIP.", details={"fileName": file_name})

        connectors_root = _connectors_root(plugin_dir)
        installed_ids: list[str] = []

        for src_root in roots:
            plugin_json = src_root / "plugin.json"
            if not plugin_json.exists():
                continue
            connector_id, _display_name, _version = _parse_manifest(plugin_json)
            target = connectors_root / connector_id
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src_root, target)
            marker = _disabled_marker(target)
            if marker.exists():
                marker.unlink()
            installed_ids.append(connector_id)

        if not installed_ids:
            raise Datam8ValidationError(message="No valid connector plugin found in ZIP.", details={"fileName": file_name})

    return {"installed": sorted(installed_ids)}


def _download_plugin_zip(url: str) -> bytes:
    u = (url or "").strip()
    if not u.lower().startswith("https://") or not u.lower().endswith(".zip"):
        raise Datam8ValidationError(message="Only https:// direct .zip URLs are supported for plugin install.", details={"url": url})
    try:
        with urllib.request.urlopen(u, timeout=30) as response:
            return response.read()
    except Exception as e:
        raise Datam8ValidationError(message="Failed to download plugin ZIP.", details={"url": u, "error": str(e)})


def install_git_url(*, plugin_dir: Path, git_url: str) -> dict[str, Any]:
    # Backward-compatible name; accepts direct https://...zip URLs.
    return install_zip(plugin_dir=plugin_dir, zip_bytes=_download_plugin_zip(git_url), file_name=None)


def set_enabled(plugin_dir: Path, plugin_id: str, enabled: bool) -> None:
    pid = (plugin_id or "").strip()
    if not pid:
        raise Datam8ValidationError(message="Plugin id is required.", details=None)
    plugin_root = _connectors_root(plugin_dir) / pid
    if not plugin_root.exists() or not plugin_root.is_dir():
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": pid})
    marker = _disabled_marker(plugin_root)
    if enabled:
        if marker.exists():
            marker.unlink()
    else:
        marker.write_text("disabled\n", encoding="utf-8")


def uninstall(plugin_dir: Path, plugin_id: str) -> None:
    pid = (plugin_id or "").strip()
    if not pid:
        raise Datam8ValidationError(message="Plugin id is required.", details=None)
    plugin_root = _connectors_root(plugin_dir) / pid
    if not plugin_root.exists() or not plugin_root.is_dir():
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": pid})
    shutil.rmtree(plugin_root)


def connectors_state(plugin_dir: Path) -> dict[str, Any]:
    return get_connectors_state(plugin_dir=plugin_dir)
