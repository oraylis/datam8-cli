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

import configparser
import hashlib
import importlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from datam8.core.connectors.plugin_host import (
    DISTRIBUTION_MARKER,
    get_connectors_state,
    load_connector_class,
    parse_connector_plugin,
)
from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError

DISABLED_MARKER = ".disabled"
CONNECTOR_ENTRYPOINT_GROUP = "datam8.connectors"
WHEEL_FILE_RE = re.compile(
    r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.!+]+(?:-[0-9][A-Za-z0-9_.]*)?-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+\.whl$"
)


@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    display_name: str
    version: str
    filename: str
    sha256: str


def default_plugin_dir() -> Path:
    """Default plugin dir.

    Returns
    -------
    Path
        Computed return value."""
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


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_wheel_name(file_name: str | None) -> str:
    name = (file_name or "").strip()
    if not name:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Wheel file name is required.",
            details=None,
        )
    if Path(name).name != name:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Wheel file name must not contain path segments.",
            details={"fileName": name},
        )
    if not name.lower().endswith(".whl"):
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Only .whl files are supported.",
            details={"fileName": name},
        )
    if not WHEEL_FILE_RE.match(name):
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Invalid wheel file name (PEP 427).",
            details={"fileName": name},
        )
    return name


def _inspect_wheel_bundle(
    *,
    wheel_bytes: bytes,
    file_name: str,
    strict_connector: bool,
) -> dict[str, str] | None:
    normalized_name = _validate_wheel_name(file_name)
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_bytes), "r") as archive:
            dist_dirs: set[str] = set()
            for name in archive.namelist():
                parts = name.split("/")
                if not parts:
                    continue
                head = parts[0]
                if head.endswith(".dist-info"):
                    dist_dirs.add(head)
            if not dist_dirs:
                raise Datam8ValidationError(
                    code="connector_distribution_invalid",
                    message="Wheel is missing .dist-info metadata.",
                    details={"fileName": normalized_name},
                )

            metadata_text: str | None = None
            entrypoints_text: str | None = None
            for dist_dir in sorted(dist_dirs):
                metadata_name = f"{dist_dir}/METADATA"
                entrypoints_name = f"{dist_dir}/entry_points.txt"
                if metadata_text is None and metadata_name in archive.namelist():
                    metadata_text = archive.read(metadata_name).decode("utf-8")
                if entrypoints_text is None and entrypoints_name in archive.namelist():
                    entrypoints_text = archive.read(entrypoints_name).decode("utf-8")

            if metadata_text is None:
                raise Datam8ValidationError(
                    code="connector_distribution_invalid",
                    message="Wheel is missing METADATA.",
                    details={"fileName": normalized_name},
                )

            msg = Parser().parsestr(metadata_text)
            project_name = (msg.get("Name") or "").strip()
            project_version = (msg.get("Version") or "").strip()
            if not project_name or not project_version:
                raise Datam8ValidationError(
                    code="connector_distribution_invalid",
                    message="Wheel METADATA must include Name and Version.",
                    details={"fileName": normalized_name},
                )

            connector_entries: list[tuple[str, str]] = []
            if entrypoints_text:
                cp = configparser.ConfigParser()
                cp.optionxform = str
                cp.read_string(entrypoints_text)
                if cp.has_section(CONNECTOR_ENTRYPOINT_GROUP):
                    for key, value in cp.items(CONNECTOR_ENTRYPOINT_GROUP):
                        k = (key or "").strip()
                        v = (value or "").strip()
                        if k and v:
                            connector_entries.append((k, v))

            if not connector_entries:
                if strict_connector:
                    raise Datam8ValidationError(
                        code="connector_distribution_invalid",
                        message="Wheel does not expose a datam8.connectors entry point.",
                        details={"fileName": normalized_name},
                    )
                return None

            if len(connector_entries) != 1:
                raise Datam8ValidationError(
                    code="connector_distribution_invalid",
                    message="Wheel must expose exactly one datam8.connectors entry point.",
                    details={"fileName": normalized_name},
                )

            connector_id, entrypoint = connector_entries[0]
            if ":" not in entrypoint:
                raise Datam8ValidationError(
                    code="connector_distribution_invalid",
                    message="Connector entry point must be in format module:Class.",
                    details={
                        "fileName": normalized_name,
                        "entrypoint": entrypoint,
                        "connectorId": connector_id,
                    },
                )

            return {
                "fileName": normalized_name,
                "projectName": project_name,
                "projectVersion": project_version,
                "connectorId": connector_id,
                "entrypoint": entrypoint,
            }
    except zipfile.BadZipFile as e:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Invalid wheel file.",
            details={"fileName": normalized_name, "error": str(e)},
        ) from e


class _SitePackagesPath:
    def __init__(self, path: Path):
        self._path = str(path)

    def __enter__(self) -> "_SitePackagesPath":
        sys.path.insert(0, self._path)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            sys.path.remove(self._path)
        except ValueError:
            pass


def _normalize_capabilities(raw: Any, *, connector_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifest capabilities must be an object.",
            details={"id": connector_id},
        )

    def as_bool(value: Any) -> bool:
        return value is True

    metadata_raw = raw.get("metadata")
    runtime_raw = raw.get("runtimeQuery")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    runtime_query = runtime_raw if isinstance(runtime_raw, dict) else {}
    return {
        "uiSchema": as_bool(raw.get("uiSchema")),
        "validateConnection": as_bool(raw.get("validateConnection")),
        "metadata": {
            "listTables": as_bool(metadata.get("listTables")),
            "getTableMetadata": as_bool(metadata.get("getTableMetadata")),
        },
        "runtimeQuery": {
            "sql": as_bool(runtime_query.get("sql")),
            "dataFrame": as_bool(runtime_query.get("dataFrame")),
        },
    }


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


def _load_manifest_from_entrypoint(
    *,
    site_packages: Path,
    connector_id: str,
    entrypoint: str,
) -> dict[str, Any]:
    mod_name, attr = entrypoint.split(":", 1)
    with _SitePackagesPath(site_packages):
        try:
            module = importlib.import_module(mod_name)
        except Exception as e:
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Failed to import connector entrypoint from installed wheel.",
                details={
                    "id": connector_id,
                    "entrypoint": entrypoint,
                    "error": str(e),
                },
            ) from e
        cls = getattr(module, attr, None)
        if cls is None or not isinstance(cls, type):
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Connector entrypoint must reference a class.",
                details={"id": connector_id, "entrypoint": entrypoint},
            )
        if not hasattr(cls, "get_manifest"):
            raise Datam8ValidationError(
                code="connector_manifest_invalid",
                message="Connector class is missing get_manifest().",
                details={"id": connector_id, "entrypoint": entrypoint},
            )
        manifest = cls.get_manifest()  # type: ignore[attr-defined]

    if not isinstance(manifest, dict):
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector get_manifest() must return an object.",
            details={"id": connector_id},
        )

    mid = (manifest.get("id") or "").strip() if isinstance(manifest.get("id"), str) else ""
    display = (
        (manifest.get("displayName") or "").strip()
        if isinstance(manifest.get("displayName"), str)
        else ""
    )
    version = (
        (manifest.get("version") or "").strip()
        if isinstance(manifest.get("version"), str)
        else ""
    )
    manifest_version_raw = manifest.get("manifestVersion", 1)
    if not isinstance(mid, str) or not mid:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifest id is required.",
            details={"entrypoint": entrypoint},
        )
    if mid != connector_id:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifest id must match datam8.connectors entrypoint key.",
            details={"entrypointId": connector_id, "manifestId": mid},
        )
    if not display:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifest displayName is required.",
            details={"id": mid},
        )
    if not version:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifest version is required.",
            details={"id": mid},
        )
    if not isinstance(manifest_version_raw, int) or manifest_version_raw < 1:
        raise Datam8ValidationError(
            code="connector_manifest_invalid",
            message="Connector manifestVersion must be a positive integer.",
            details={"id": mid},
        )

    return {
        "id": mid,
        "displayName": display,
        "version": version,
        "manifestVersion": manifest_version_raw,
        "capabilities": _normalize_capabilities(
            manifest.get("capabilities"),
            connector_id=mid,
        ),
        "dataTypeMapping": _normalize_data_type_mapping(manifest.get("dataTypeMapping")),
    }


def _pip_install_wheel(
    *,
    wheel_file: Path,
    target_dir: Path,
    wheelhouse: Path | None,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-compile",
        "--upgrade",
        "--target",
        str(target_dir),
    ]
    if wheelhouse and wheelhouse.exists() and wheelhouse.is_dir():
        cmd.extend(["--find-links", str(wheelhouse)])
    cmd.append(str(wheel_file))
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    result = _run(cmd)
    if result.returncode != 0 and "No module named pip" in (result.stderr or ""):
        ensure = _run([sys.executable, "-m", "ensurepip", "--upgrade"])
        if ensure.returncode == 0:
            result = _run(cmd)
    if result.returncode == 0:
        return
    raise Datam8ValidationError(
        code="connector_distribution_invalid",
        message="Failed to install connector wheel.",
        details={
            "fileName": wheel_file.name,
            "stdout": (result.stdout or "")[-4000:],
            "stderr": (result.stderr or "")[-4000:],
        },
    )


def _write_plugin_json(
    *,
    plugin_root: Path,
    manifest: dict[str, Any],
    entrypoint: str,
) -> None:
    payload = {
        "pluginType": "connector",
        "id": manifest["id"],
        "displayName": manifest["displayName"],
        "version": manifest["version"],
        "manifestVersion": manifest["manifestVersion"],
        "entrypoint": entrypoint,
        "capabilities": manifest["capabilities"],
        "dataTypeMapping": manifest.get("dataTypeMapping") or [],
    }
    (plugin_root / "plugin.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_distribution_metadata(*, plugin_root: Path, file_name: str, sha256: str, install_source: str) -> None:
    marker = plugin_root / DISTRIBUTION_MARKER
    marker.write_text(
        json.dumps(
            {
                "type": "wheel",
                "filename": file_name,
                "sha256": sha256,
                "installSource": install_source,
            }
        ),
        encoding="utf-8",
    )


def _install_wheel_from_bytes(
    *,
    plugin_dir: Path,
    wheel_bytes: bytes,
    file_name: str,
    install_source: str,
    wheelhouse: Path | None = None,
) -> dict[str, Any]:
    info = _inspect_wheel_bundle(
        wheel_bytes=wheel_bytes,
        file_name=file_name,
        strict_connector=True,
    )
    if info is None:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Wheel does not expose a connector entrypoint.",
            details={"fileName": file_name},
        )

    normalized_name = info["fileName"]
    connector_id = info["connectorId"]
    entrypoint = info["entrypoint"]
    sha256 = _sha256_hex(wheel_bytes)

    with tempfile.TemporaryDirectory(prefix="datam8-connector-wheel-install-") as td:
        temp_root = Path(td)
        wheel_file = temp_root / normalized_name
        wheel_file.write_bytes(wheel_bytes)
        site_packages = temp_root / "site-packages"
        _pip_install_wheel(
            wheel_file=wheel_file,
            target_dir=site_packages,
            wheelhouse=wheelhouse,
        )
        manifest = _load_manifest_from_entrypoint(
            site_packages=site_packages,
            connector_id=connector_id,
            entrypoint=entrypoint,
        )

        connectors_root = _connectors_root(plugin_dir)
        plugin_root = connectors_root / connector_id
        if plugin_root.exists():
            shutil.rmtree(plugin_root)
        (plugin_root / "site-packages").parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(site_packages, plugin_root / "site-packages")
        _write_plugin_json(
            plugin_root=plugin_root,
            manifest=manifest,
            entrypoint=entrypoint,
        )
        marker = _disabled_marker(plugin_root)
        if marker.exists():
            marker.unlink()
        _write_distribution_metadata(
            plugin_root=plugin_root,
            file_name=normalized_name,
            sha256=sha256,
            install_source=install_source,
        )

    return {"installed": [connector_id], "sha256": sha256}


def verify_wheel_bundle(*, wheel_bytes: bytes, file_name: str | None = None) -> PluginDescriptor:
    """Verify wheel bundle metadata."""
    info = _inspect_wheel_bundle(
        wheel_bytes=wheel_bytes,
        file_name=file_name or "",
        strict_connector=True,
    )
    if info is None:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Wheel does not expose a connector entrypoint.",
            details={"fileName": file_name},
        )

    return PluginDescriptor(
        id=info["connectorId"],
        display_name=info["projectName"],
        version=info["projectVersion"],
        filename=info["fileName"],
        sha256=_sha256_hex(wheel_bytes),
    )


def list_plugins(plugin_dir: Path) -> dict[str, Any]:
    """List plugins.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value."""
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
            parsed = parse_connector_plugin(folder)
            item["id"] = parsed.id
            item["name"] = parsed.display_name
            item["displayName"] = parsed.display_name
            item["version"] = parsed.version
            item["manifestVersion"] = parsed.manifest_version
            item["capabilities"] = parsed.capabilities
            item["distribution"] = parsed.distribution or {"type": "wheel", "filename": "", "sha256": ""}
            item["installSource"] = parsed.install_source
            if parsed.id != folder.name:
                errors[parsed.id] = f"Plugin folder name '{folder.name}' does not match plugin id '{parsed.id}'."
            else:
                if enabled:
                    load_connector_class(parsed)
        except Exception as e:
            errors[item["id"]] = str(e)
        plugins.append(item)

    plugins.sort(key=lambda p: str(p.get("id", "")).lower())
    return {"pluginDir": str(plugin_dir), "plugins": plugins, "errors": errors}


def reload(plugin_dir: Path) -> dict[str, Any]:
    """Reload.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value."""
    return list_plugins(plugin_dir)


def install_wheel(*, plugin_dir: Path, wheel_bytes: bytes, file_name: str | None = None) -> dict[str, Any]:
    """Install a connector wheel from raw bytes."""
    normalized_name = _validate_wheel_name(file_name)
    return _install_wheel_from_bytes(
        plugin_dir=plugin_dir,
        wheel_bytes=wheel_bytes,
        file_name=normalized_name,
        install_source="upload",
        wheelhouse=None,
    )


def _download_plugin_wheel(url: str) -> bytes:
    u = (url or "").strip()
    if not u.lower().startswith("https://") or not u.lower().endswith(".whl"):
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Only https:// direct .whl URLs are supported for plugin install.",
            details={"url": url},
        )
    try:
        with urllib.request.urlopen(u, timeout=30) as response:
            return response.read()
    except Exception as e:
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="Failed to download connector wheel.",
            details={"url": u, "error": str(e)},
        ) from e


def install_wheel_url(*, plugin_dir: Path, url: str, sha256: str) -> dict[str, Any]:
    """Install connector wheel by URL + expected sha256."""
    expected = (sha256 or "").strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise Datam8ValidationError(
            code="connector_distribution_invalid",
            message="sha256 must be a 64-character lowercase hex string.",
            details=None,
        )
    wheel_bytes = _download_plugin_wheel(url)
    actual = _sha256_hex(wheel_bytes)
    if actual != expected:
        raise Datam8ValidationError(
            code="connector_distribution_hash_mismatch",
            message="Wheel sha256 mismatch.",
            details={"expected": expected, "actual": actual, "url": url},
        )
    file_name = Path(url).name
    return _install_wheel_from_bytes(
        plugin_dir=plugin_dir,
        wheel_bytes=wheel_bytes,
        file_name=file_name,
        install_source="index",
        wheelhouse=None,
    )


def install_zip(*, plugin_dir: Path, zip_bytes: bytes, file_name: str | None = None) -> dict[str, Any]:
    """Deprecated: ZIP is no longer supported."""
    _ = plugin_dir
    _ = zip_bytes
    _ = file_name
    raise Datam8ValidationError(
        code="connector_distribution_invalid",
        message="ZIP connector installation is no longer supported. Use .whl.",
        details=None,
    )


def install_git_url(*, plugin_dir: Path, git_url: str) -> dict[str, Any]:
    """Deprecated: git URL installs are no longer supported."""
    _ = plugin_dir
    _ = git_url
    raise Datam8ValidationError(
        code="connector_distribution_invalid",
        message="Git URL connector installation is no longer supported. Provide a wheel URL with sha256.",
        details=None,
    )


def verify_zip_bundle(*, zip_bytes: bytes) -> PluginDescriptor:
    """Deprecated: ZIP verification is no longer supported."""
    _ = zip_bytes
    raise Datam8ValidationError(
        code="connector_distribution_invalid",
        message="ZIP connector bundles are no longer supported. Use .whl.",
        details=None,
    )


def set_enabled(plugin_dir: Path, plugin_id: str, enabled: bool) -> None:
    """Set enabled.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.
    plugin_id : str
        plugin_id parameter value.
    enabled : bool
        enabled parameter value.

    Returns
    -------
    None
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails.
    Datam8ValidationError
        Raised when validation or runtime execution fails."""
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
    """Uninstall.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.
    plugin_id : str
        plugin_id parameter value.

    Returns
    -------
    None
        Computed return value.

    Raises
    ------
    Datam8NotFoundError
        Raised when validation or runtime execution fails.
    Datam8ValidationError
        Raised when validation or runtime execution fails."""
    pid = (plugin_id or "").strip()
    if not pid:
        raise Datam8ValidationError(message="Plugin id is required.", details=None)
    plugin_root = _connectors_root(plugin_dir) / pid
    if not plugin_root.exists() or not plugin_root.is_dir():
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": pid})
    try:
        shutil.rmtree(plugin_root)
    except PermissionError:
        # Windows can keep short-lived file handles after import; disable plugin as fallback.
        _disabled_marker(plugin_root).write_text("disabled\n", encoding="utf-8")


def connectors_state(plugin_dir: Path) -> dict[str, Any]:
    """Connectors state.

    Parameters
    ----------
    plugin_dir : Path
        plugin_dir parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value."""
    return get_connectors_state(plugin_dir=plugin_dir)
