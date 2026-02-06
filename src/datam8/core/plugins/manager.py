from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from datam8.core.atomic import atomic_write_json, atomic_write_text
from datam8.core.connectors.registry import ConnectorSource, connector_registry
from datam8.core.connectors.types import ConnectorModule
from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8NotFoundError,
    Datam8ValidationError,
)

def default_plugin_dir() -> Path:
    base = Path(user_data_dir(appname="datam8", appauthor=False))
    plugin_dir = base / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return plugin_dir


def _registry_path(plugin_dir: Path) -> Path:
    return plugin_dir / "registry.json"


def _empty_registry() -> dict[str, Any]:
    return {"schemaVersion": 1, "plugins": []}


def read_registry(plugin_dir: Path) -> dict[str, Any]:
    p = _registry_path(plugin_dir)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schemaVersion") != 1 or not isinstance(data.get("plugins"), list):
            return _empty_registry()
        return data
    except Exception:
        return _empty_registry()


def write_registry(plugin_dir: Path, data: dict[str, Any]) -> None:
    atomic_write_json(_registry_path(plugin_dir), data, indent=2)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_safe_plugin_id(pid: str) -> bool:
    return bool(__import__("re").match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", pid or ""))


def _safe_relpath(dest: Path, zip_name: str) -> Path:
    dest_abs = dest.resolve()
    name = (zip_name or "").replace("\\", "/")
    if not name or name.startswith("/") or name.startswith("\\"):
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    parts = [p for p in name.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    rel = Path(*parts)
    target = (dest / rel).resolve()
    if os.path.commonpath([str(dest_abs), str(target)]) != str(dest_abs):
        raise Datam8ValidationError(message="Unsafe ZIP entry (zip-slip).", details={"entry": zip_name})
    return rel


def _read_zip_text(zip_bytes: bytes, path: str) -> str | None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        if path not in z.namelist():
            return None
        raw = z.read(path)
        try:
            return raw.decode("utf-8")
        except Exception:
            return None


def _read_zip_json(zip_bytes: bytes, path: str) -> dict[str, Any] | None:
    raw = _read_zip_text(zip_bytes, path)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    name: str
    version: str
    entrypoint: str
    connector_ids: list[str]
    min_datam8_version: str | None = None


def _parse_plugin_json(data: dict[str, Any]) -> PluginDescriptor:
    pid = data.get("id")
    name = data.get("name")
    version = data.get("version")
    typ = data.get("type")
    entrypoint = data.get("entrypoint")
    connector_ids = data.get("connectorIds")
    min_ver = data.get("min_datam8_version")

    if not isinstance(pid, str) or not pid.strip() or not _is_safe_plugin_id(pid.strip()):
        raise Datam8ValidationError(message="Invalid plugin id.", details={"id": pid})
    if not isinstance(name, str) or not name.strip():
        raise Datam8ValidationError(message="Invalid plugin name.", details={"name": name})
    if not isinstance(version, str) or not version.strip():
        raise Datam8ValidationError(message="Invalid plugin version.", details={"version": version})
    if typ != "connector":
        raise Datam8ValidationError(message="plugin.json type must be 'connector'.", details={"type": typ})
    if not isinstance(entrypoint, str) or ":" not in entrypoint or not entrypoint.strip():
        raise Datam8ValidationError(message="Invalid entrypoint (expected 'pkg.module:func').", details={"entrypoint": entrypoint})
    if not isinstance(connector_ids, list) or not all(isinstance(x, str) and x.strip() for x in connector_ids):
        raise Datam8ValidationError(message="connectorIds must be a list of strings.", details=None)

    connector_ids_norm = []
    for cid in [pid.strip(), *[x.strip() for x in connector_ids]]:
        if cid and cid not in connector_ids_norm:
            connector_ids_norm.append(cid)

    if min_ver is not None and not isinstance(min_ver, str):
        raise Datam8ValidationError(message="min_datam8_version must be a string.", details=None)

    return PluginDescriptor(
        id=pid.strip(),
        name=name.strip(),
        version=version.strip(),
        entrypoint=entrypoint.strip(),
        connector_ids=connector_ids_norm,
        min_datam8_version=min_ver.strip() if isinstance(min_ver, str) and min_ver.strip() else None,
    )


def verify_zip_bundle(*, zip_bytes: bytes) -> PluginDescriptor:
    plugin_json = _read_zip_json(zip_bytes, "plugin.json")
    if not plugin_json:
        raise Datam8ValidationError(message="Plugin bundle is missing plugin.json.", details=None)

    checksums_text = _read_zip_text(zip_bytes, "checksums/sha256.txt")
    if not checksums_text:
        raise Datam8ValidationError(message="Plugin bundle is missing checksums/sha256.txt.", details=None)

    desc = _parse_plugin_json(plugin_json)

    expected: dict[str, str] = {}
    for raw_line in checksums_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise Datam8ValidationError(message="Invalid checksums/sha256.txt line.", details={"line": raw_line})
        sha = parts[0].strip().lower()
        rel = parts[1].lstrip("*").strip()
        if not sha or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise Datam8ValidationError(message="Invalid sha256 in checksums file.", details={"line": raw_line})
        if not rel or rel.endswith("/"):
            raise Datam8ValidationError(message="Invalid path in checksums file.", details={"line": raw_line})
        if rel in expected:
            raise Datam8ValidationError(message="Duplicate checksum entry.", details={"path": rel})
        expected[rel] = sha

    if "plugin.json" not in expected:
        raise Datam8ValidationError(message="checksums/sha256.txt must include plugin.json.", details=None)

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        files = [n for n in z.namelist() if not n.endswith("/")]
        files_norm = [n.replace("\\", "/") for n in files]

        # Safety preflight (zip-slip)
        for name in files_norm:
            _safe_relpath(Path("."), name)

        # Enforce full coverage: all files except checksums/sha256.txt must be listed.
        for name in files_norm:
            if name == "checksums/sha256.txt":
                continue
            if name not in expected:
                raise Datam8ValidationError(message="File missing from checksums list.", details={"path": name})

        # Enforce no extra checksum entries.
        for rel in expected.keys():
            if rel == "checksums/sha256.txt":
                continue
            if rel not in set(files_norm):
                raise Datam8ValidationError(message="Checksum entry references missing file.", details={"path": rel})

        # Verify hashes.
        for rel, want in expected.items():
            if rel == "checksums/sha256.txt":
                continue
            got = hashlib.sha256(z.read(rel)).hexdigest()
            if got != want:
                raise Datam8ValidationError(
                    code="plugin_checksum_mismatch",
                    message="Plugin bundle checksum mismatch.",
                    details={"path": rel, "expected": want, "actual": got},
                )

    return desc


def _safe_extract(*, zip_bytes: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        dest.mkdir(parents=True, exist_ok=True)
        for info in z.infolist():
            rel = _safe_relpath(dest, info.filename)
            target = dest / rel
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def install_zip(
    *,
    plugin_dir: Path,
    zip_bytes: bytes,
    file_name: str | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    desc = verify_zip_bundle(zip_bytes=zip_bytes)
    sha = _sha256(zip_bytes)

    install_root = plugin_dir / desc.id / desc.version
    if install_root.exists():
        shutil.rmtree(install_root)
    _safe_extract(zip_bytes=zip_bytes, dest=install_root)
    atomic_write_text(install_root / "bundle.sha256", sha + "\n")

    now_ms = int(__import__("time").time() * 1000)

    reg = read_registry(plugin_dir)
    plugins = [p for p in reg.get("plugins", []) if isinstance(p, dict)]
    plugins = [p for p in plugins if p.get("id") != desc.id]

    entry = {
        "id": desc.id,
        "enabled": True,
        "entry": f"{desc.id}/{desc.version}/plugin.json",
        "installedAt": now_ms,
        "updatedAt": now_ms,
        "source": source if isinstance(source, dict) else ({"kind": "zip", "fileName": file_name} if file_name else {"kind": "zip"}),
        "version": desc.version,
        "sha256": sha,
        "name": desc.name,
        "connectorIds": desc.connector_ids,
    }
    plugins.append(entry)
    reg["plugins"] = plugins
    write_registry(plugin_dir, reg)
    return entry


def _download_plugin_zip(url: str) -> bytes:
    u = (url or "").strip()
    if not u.lower().startswith("https://") or not u.lower().endswith(".zip"):
        raise Datam8ValidationError(message="Only https:// direct .zip URLs are supported for plugin install.", details={"url": url})
    try:
        try:
            import httpx  # type: ignore
        except ModuleNotFoundError as e:
            raise Datam8ExternalSystemError(
                code="missing_dependency",
                message="Plugin download requires optional dependency 'httpx'.",
                details={"package": "httpx"},
                hint="Install missing Python dependencies for plugin download, or install plugins from a local zip file instead.",
            ) from e
        res = httpx.get(u, timeout=30.0, follow_redirects=True)
        res.raise_for_status()
        return res.content
    except Exception as e:
        raise Datam8ExternalSystemError(code="plugin_download_failed", message="Failed to download plugin ZIP.", details={"url": url, "error": str(e)})


def install_git_url(*, plugin_dir: Path, git_url: str) -> dict[str, Any]:
    zip_bytes = _download_plugin_zip(git_url)
    entry = install_zip(plugin_dir=plugin_dir, zip_bytes=zip_bytes, file_name=None, source={"kind": "git", "url": git_url})
    return entry


def set_enabled(plugin_dir: Path, plugin_id: str, enabled: bool) -> None:
    reg = read_registry(plugin_dir)
    found = False
    for p in reg.get("plugins", []):
        if isinstance(p, dict) and p.get("id") == plugin_id:
            p["enabled"] = bool(enabled)
            p["updatedAt"] = int(__import__("time").time() * 1000)
            found = True
    if not found:
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": plugin_id})
    write_registry(plugin_dir, reg)


def uninstall(plugin_dir: Path, plugin_id: str) -> None:
    reg = read_registry(plugin_dir)
    reg["plugins"] = [p for p in reg.get("plugins", []) if not (isinstance(p, dict) and p.get("id") == plugin_id)]
    write_registry(plugin_dir, reg)

    install_root = plugin_dir / plugin_id
    if install_root.exists():
        shutil.rmtree(install_root)


def _call_entrypoint(*, plugin_root: Path, entrypoint: str) -> list[ConnectorModule]:
    py_root = plugin_root / "python"
    if not py_root.exists() or not py_root.is_dir():
        raise Datam8ValidationError(message="Plugin bundle is missing python/ directory.", details={"pluginRoot": str(plugin_root)})

    mod_name, fn_name = entrypoint.split(":", 1)
    sys.path.insert(0, str(py_root))
    try:
        import importlib

        # Different plugins may ship the same entrypoint module name.
        # Drop cached modules so each plugin resolves against its own python/ dir.
        for key in list(sys.modules.keys()):
            if key == mod_name or key.startswith(f"{mod_name}."):
                sys.modules.pop(key, None)
        importlib.invalidate_caches()

        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            raise Datam8ValidationError(message="Plugin entrypoint is not callable.", details={"entrypoint": entrypoint})
        result = fn()
        if not isinstance(result, list):
            raise Datam8ValidationError(message="Plugin entrypoint must return a list of connectors.", details={"entrypoint": entrypoint})

        out: list[ConnectorModule] = []
        for item in result:
            if isinstance(item, ConnectorModule):
                out.append(item)
                continue
            if isinstance(item, dict) and isinstance(item.get("manifest"), dict) and callable(item.get("create_connector")):
                out.append(ConnectorModule(manifest=item["manifest"], create_connector=item["create_connector"]))
                continue
            raise Datam8ValidationError(message="Invalid connector entry returned by plugin.", details={"entrypoint": entrypoint})
        return out
    finally:
        try:
            sys.path.remove(str(py_root))
        except ValueError:
            pass


def reload(plugin_dir: Path) -> dict[str, Any]:
    connector_registry.unregister_all_plugins()

    reg = read_registry(plugin_dir)
    errors: dict[str, str] = {}

    for p in reg.get("plugins", []):
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        if not p.get("enabled", False):
            continue

        entry_path = p.get("entry")
        if not isinstance(entry_path, str) or not entry_path.strip():
            errors[pid] = "Missing plugin entry path."
            continue

        try:
            entry = Path(entry_path)
            if not entry.is_absolute():
                entry = plugin_dir / entry_path
            if not entry.exists():
                raise Datam8NotFoundError(message="Plugin entry not found on disk.", details={"entry": str(entry)})

            # Entry is expected to be <plugin_dir>/<id>/<version>/plugin.json
            plugin_root = entry.parent

            desc_data = json.loads(entry.read_text(encoding="utf-8"))
            desc = _parse_plugin_json(desc_data if isinstance(desc_data, dict) else {})
            if desc.id != pid:
                raise Datam8ValidationError(message="Plugin id does not match plugin.json.", details={"expected": pid, "actual": desc.id})

            modules = _call_entrypoint(plugin_root=plugin_root, entrypoint=desc.entrypoint)
            for mod in modules:
                name = (mod.manifest or {}).get("name")
                if not isinstance(name, str) or not name.strip():
                    raise Datam8ValidationError(message="Plugin connector is missing manifest.name.", details={"pluginId": pid})
                cid = name.strip()
                if cid not in desc.connector_ids:
                    raise Datam8ValidationError(
                        message="Plugin returned connector not listed in plugin.json connectorIds.",
                        details={"connectorId": cid, "pluginId": pid},
                    )
                connector_registry.register(mod, ConnectorSource(kind="plugin", pluginId=pid, entryPath=str(entry)))

            if p.get("lastError"):
                p.pop("lastError", None)
                p.pop("lastErrorAt", None)
        except Exception as e:
            msg = str(e) or "Failed to load plugin."
            errors[pid] = msg
            p["lastError"] = msg
            p["lastErrorAt"] = int(__import__("time").time() * 1000)

    write_registry(plugin_dir, reg)
    return {"pluginDir": str(plugin_dir), "plugins": reg.get("plugins", []), "errors": errors}
