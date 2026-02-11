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

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import keyring  # type: ignore
    from keyring.errors import PasswordDeleteError  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyring = None  # type: ignore[assignment]
    PasswordDeleteError = Exception  # type: ignore[assignment]

from datam8.core.atomic import atomic_write_json
from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8NotFoundError,
    Datam8ValidationError,
)
from datam8.core.paths import resolve_solution

SERVICE_NAME = "datam8"


@dataclass(frozen=True)
class SecretRef:
    scheme: str
    scope: str
    name: str

    def to_uri(self) -> str:
        return f"secretRef://{self.scheme}/{self.scope}/{self.name}"


def solution_scope(solution_path: str | None) -> str:
    """Solution scope.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.

    Returns
    -------
    str
        Computed return value."""
    resolved = resolve_solution(solution_path or os.environ.get("DATAM8_SOLUTION_PATH"))
    p = str(resolved.solution_file).replace("\\", "/").lower().strip()
    h = hashlib.sha256(p.encode("utf-8")).hexdigest()
    return f"sol-{h[:16]}"


def _registry_path() -> Path:
    base = Path.home() / ".datam8"
    base.mkdir(parents=True, exist_ok=True)
    return base / "secrets.registry.v1.json"


def _load_registry() -> dict[str, Any]:
    p = _registry_path()
    if not p.exists():
        return {"schemaVersion": 1, "entries": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schemaVersion") != 1 or not isinstance(data.get("entries"), list):
            return {"schemaVersion": 1, "entries": []}
        return data
    except Exception:
        return {"schemaVersion": 1, "entries": []}


def _save_registry(data: dict[str, Any]) -> None:
    atomic_write_json(_registry_path(), data, indent=2)


def is_keyring_available() -> bool:
    """Is keyring available.

    Returns
    -------
    bool
        Computed return value."""
    if keyring is None:
        return False
    try:
        _ = keyring.get_keyring()
        return True
    except Exception:
        return False


def _keyring_get(name: str) -> str | None:
    if keyring is None:
        return None
    return keyring.get_password(SERVICE_NAME, name)


def _keyring_set(name: str, value: str) -> None:
    if keyring is None:
        raise Datam8ExternalSystemError(
            code="secrets_unavailable",
            message="Secure secret storage is not available (keyring backend missing/unavailable).",
            details=None,
            hint="Install/configure keyring for your OS.",
        )
    keyring.set_password(SERVICE_NAME, name, value)


def _keyring_delete(name: str) -> None:
    if keyring is None:
        raise Datam8ExternalSystemError(
            code="secrets_unavailable",
            message="Secure secret storage is not available (keyring backend missing/unavailable).",
            details=None,
            hint="Install/configure keyring for your OS.",
        )
    try:
        keyring.delete_password(SERVICE_NAME, name)
    except PasswordDeleteError:
        raise Datam8NotFoundError(message="Secret not found.", details={"name": name})


def _secret_name(scope: str, data_source: str, key: str) -> str:
    ds = (data_source or "").strip()
    k = (key or "").strip()
    if not ds or not k:
        raise Datam8ValidationError(message="dataSourceName and key are required.", details={"dataSourceName": data_source, "key": key})
    return f"runtime:{scope}:{ds}:{k}"


def list_runtime_secret_keys(solution_path: str | None, data_source_name: str) -> list[dict[str, Any]]:
    """List runtime secret keys.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.
    data_source_name : str
        data_source_name parameter value.

    Returns
    -------
    list[dict[str, Any]]
        Computed return value."""
    scope = solution_scope(solution_path)
    reg = _load_registry()
    out = []
    for e in reg["entries"]:
        if not isinstance(e, dict):
            continue
        if e.get("kind") != "runtime":
            continue
        if e.get("scope") != scope:
            continue
        if e.get("dataSourceName") != data_source_name:
            continue
        out.append(e)
    out.sort(key=lambda x: str(x.get("key", "")).lower())
    return out


def set_runtime_secret(
    *,
    solution_path: str | None,
    data_source_name: str,
    key: str,
    value: str,
) -> SecretRef:
    """Set runtime secret.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.
    data_source_name : str
        data_source_name parameter value.
    key : str
        key parameter value.
    value : str
        value parameter value.

    Returns
    -------
    SecretRef
        Computed return value.

    Raises
    ------
    Datam8ExternalSystemError
        Raised when validation or runtime execution fails."""
    if not is_keyring_available():
        raise Datam8ExternalSystemError(
            code="secrets_unavailable",
            message="Secure secret storage is not available (keyring backend missing/unavailable).",
            details=None,
            hint="Install/configure keyring for your OS.",
        )
    scope = solution_scope(solution_path)
    name = _secret_name(scope, data_source_name, key)
    _keyring_set(name, value)

    reg = _load_registry()
    entry = {
        "kind": "runtime",
        "scope": scope,
        "dataSourceName": data_source_name,
        "key": key,
        "secretRef": SecretRef(scheme="keyring", scope=scope, name=name).to_uri(),
        "updatedAt": int(time.time() * 1000),
    }
    reg["entries"] = [e for e in reg["entries"] if not (isinstance(e, dict) and e.get("kind") == "runtime" and e.get("scope") == scope and e.get("dataSourceName") == data_source_name and e.get("key") == key)]
    reg["entries"].append(entry)
    _save_registry(reg)
    return SecretRef(scheme="keyring", scope=scope, name=name)


def delete_runtime_secret(*, solution_path: str | None, data_source_name: str, key: str) -> None:
    """Delete runtime secret.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.
    data_source_name : str
        data_source_name parameter value.
    key : str
        key parameter value.

    Returns
    -------
    None
        Computed return value.

    Raises
    ------
    Datam8ExternalSystemError
        Raised when validation or runtime execution fails."""
    if not is_keyring_available():
        raise Datam8ExternalSystemError(
            code="secrets_unavailable",
            message="Secure secret storage is not available (keyring backend missing/unavailable).",
            details=None,
            hint="Install/configure keyring for your OS.",
        )
    scope = solution_scope(solution_path)
    name = _secret_name(scope, data_source_name, key)
    _keyring_delete(name)
    reg = _load_registry()
    reg["entries"] = [e for e in reg["entries"] if not (isinstance(e, dict) and e.get("kind") == "runtime" and e.get("scope") == scope and e.get("dataSourceName") == data_source_name and e.get("key") == key)]
    _save_registry(reg)


def get_runtime_secret(
    *,
    solution_path: str | None,
    data_source_name: str,
    key: str,
    reveal: bool = False,
) -> dict[str, Any]:
    """Get runtime secret.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.
    data_source_name : str
        data_source_name parameter value.
    key : str
        key parameter value.
    reveal : bool
        reveal parameter value.

    Returns
    -------
    dict[str, Any]
        Computed return value."""
    scope = solution_scope(solution_path)
    name = _secret_name(scope, data_source_name, key)
    reg_entries = list_runtime_secret_keys(solution_path, data_source_name)
    secret_ref = None
    for e in reg_entries:
        if e.get("key") == key:
            secret_ref = e.get("secretRef")
            break
    present = False
    value = None
    if is_keyring_available():
        v = _keyring_get(name)
        if v is not None:
            present = True
            if reveal:
                value = v

    return {
        "scope": scope,
        "dataSourceName": data_source_name,
        "key": key,
        "present": present,
        "secretRef": secret_ref or SecretRef(scheme="keyring", scope=scope, name=name).to_uri(),
        "value": value if reveal else None,
    }


def get_runtime_secrets_map(
    *,
    solution_path: str | None,
    data_source_name: str,
    include_values: bool = True,
    override: dict[str, str] | None = None,
) -> dict[str, str]:
    """Get runtime secrets map.

    Parameters
    ----------
    solution_path : str | None
        solution_path parameter value.
    data_source_name : str
        data_source_name parameter value.
    include_values : bool
        include_values parameter value.
    override : dict[str, str] | None
        override parameter value.

    Returns
    -------
    dict[str, str]
        Computed return value."""
    override = override or {}
    items = list_runtime_secret_keys(solution_path, data_source_name)
    result: dict[str, str] = {}
    for e in items:
        k = e.get("key")
        if not isinstance(k, str) or not k:
            continue
        if k in override and override[k].strip():
            result[k] = override[k].strip()
            continue
        if not include_values:
            continue
        scope = solution_scope(solution_path)
        name = _secret_name(scope, data_source_name, k)
        if is_keyring_available():
            v = _keyring_get(name)
            if isinstance(v, str) and v.strip():
                result[k] = v
    return result


def is_secret_ref(value: str) -> bool:
    """Is secret ref.

    Parameters
    ----------
    value : str
        value parameter value.

    Returns
    -------
    bool
        Computed return value."""
    return isinstance(value, str) and value.strip().lower().startswith("secretref://")


def runtime_secret_ref(*, data_source_name: str, key: str) -> str:
    """Runtime secret ref.

    Parameters
    ----------
    data_source_name : str
        data_source_name parameter value.
    key : str
        key parameter value.

    Returns
    -------
    str
        Computed return value.

    Raises
    ------
    Datam8ValidationError
        Raised when validation or runtime execution fails."""
    ds = (data_source_name or "").strip()
    k = (key or "").strip()
    if not ds or not k:
        raise Datam8ValidationError(message="dataSourceName and key are required.", details={"dataSourceName": data_source_name, "key": key})
    # Portable reference: does not embed solution scope / absolute paths.
    return SecretRef(scheme="runtime", scope=ds, name=k).to_uri()


def _parse_secret_ref_uri(uri: str) -> SecretRef:
    raw = (uri or "").strip()
    if not raw.lower().startswith("secretref://"):
        raise Datam8ValidationError(message="Invalid secretRef URI.", details={"uri": uri})
    rest = raw[len("secretRef://") :]
    parts = [p for p in rest.split("/") if p]
    if len(parts) < 3:
        raise Datam8ValidationError(message="Invalid secretRef URI (expected secretRef://<scheme>/<scope>/<name>).", details={"uri": uri})
    scheme = parts[0]
    scope = parts[1]
    name = "/".join(parts[2:])
    return SecretRef(scheme=scheme, scope=scope, name=name)


def resolve_secret_ref(*, solution_path: str | None, value: str) -> str:
    """
    Resolves `secretRef://...` references to plaintext values for connector execution.
    Non-secretRef values are returned unchanged.
    """
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    if not is_secret_ref(raw):
        return raw

    ref = _parse_secret_ref_uri(raw)
    if not is_keyring_available():
        raise Datam8ExternalSystemError(
            code="secrets_unavailable",
            message="Secure secret storage is not available (keyring backend missing/unavailable).",
            details={"secretRef": raw},
            hint="Install/configure keyring for your OS.",
        )

    if ref.scheme == "runtime":
        data_source_name = ref.scope
        key = ref.name
        scope = solution_scope(solution_path)
        name = _secret_name(scope, data_source_name, key)
        v = _keyring_get(name)
        if v is None:
            raise Datam8NotFoundError(message="Secret not found.", details={"secretRef": raw})
        return v

    if ref.scheme == "keyring":
        v = _keyring_get(ref.name)
        if v is None:
            raise Datam8NotFoundError(message="Secret not found.", details={"secretRef": raw})
        return v

    raise Datam8ValidationError(message="Unsupported secretRef scheme.", details={"scheme": ref.scheme, "secretRef": raw})
