from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    try:
        import keyring  # type: ignore

        _ = keyring.get_keyring()
        return True
    except Exception:
        return False


def _keyring_get(name: str) -> str | None:
    import keyring  # type: ignore

    return keyring.get_password(SERVICE_NAME, name)


def _keyring_set(name: str, value: str) -> None:
    import keyring  # type: ignore

    keyring.set_password(SERVICE_NAME, name, value)


def _keyring_delete(name: str) -> None:
    import keyring  # type: ignore

    try:
        keyring.delete_password(SERVICE_NAME, name)
    except keyring.errors.PasswordDeleteError:
        raise Datam8NotFoundError(message="Secret not found.", details={"name": name})


def _secret_name(scope: str, data_source: str, key: str) -> str:
    ds = (data_source or "").strip()
    k = (key or "").strip()
    if not ds or not k:
        raise Datam8ValidationError(message="dataSourceName and key are required.", details={"dataSourceName": data_source, "key": key})
    return f"runtime:{scope}:{ds}:{k}"


def list_runtime_secret_keys(solution_path: str | None, data_source_name: str) -> list[dict[str, Any]]:
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
        "updatedAt": int(__import__("time").time() * 1000),
    }
    reg["entries"] = [e for e in reg["entries"] if not (isinstance(e, dict) and e.get("kind") == "runtime" and e.get("scope") == scope and e.get("dataSourceName") == data_source_name and e.get("key") == key)]
    reg["entries"].append(entry)
    _save_registry(reg)
    return SecretRef(scheme="keyring", scope=scope, name=name)


def delete_runtime_secret(*, solution_path: str | None, data_source_name: str, key: str) -> None:
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
