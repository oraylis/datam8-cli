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

from typing import Any

from datam8.core.connectors.types import ValidationResult


def _get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def validate_connection_config(manifest: dict[str, Any], raw_config: Any) -> ValidationResult:
    """Validate connection config.

    Parameters
    ----------
    manifest : dict[str, Any]
        manifest parameter value.
    raw_config : Any
        raw_config parameter value.

    Returns
    -------
    ValidationResult
        Computed return value."""
    cfg = raw_config if isinstance(raw_config, dict) else {}
    schema = manifest.get("connectionSchema") if isinstance(manifest, dict) else None
    errors: list[dict[str, str]] = []

    def req(path: str, message: str) -> None:
        errors.append({"path": path, "message": message})

    fields = []
    if isinstance(schema, dict) and isinstance(schema.get("fields"), list):
        fields = schema["fields"]
    for f in fields:
        if not isinstance(f, dict):
            continue
        path = f.get("path")
        if not isinstance(path, str) or not path:
            continue
        if f.get("required") is True:
            val = _get_by_path(cfg, path)
            missing = val is None or (isinstance(val, str) and not val.strip())
            if missing:
                req(path, "Required field is missing.")

    variants = schema.get("variants") if isinstance(schema, dict) else None
    discriminator_path = variants.get("discriminatorPath") if isinstance(variants, dict) else None
    if isinstance(variants, dict) and isinstance(variants.get("variants"), list) and isinstance(discriminator_path, str):
        disc = _get_by_path(cfg, discriminator_path)
        if disc is None:
            req(discriminator_path, "Required discriminator is missing.")
        else:
            match = None
            for v in variants["variants"]:
                if isinstance(v, dict) and v.get("discriminatorValue") == disc:
                    match = v
                    break
            if match and isinstance(match.get("fields"), list):
                for f in match["fields"]:
                    if not isinstance(f, dict):
                        continue
                    path = f.get("path")
                    if not isinstance(path, str) or not path:
                        continue
                    if f.get("required") is True:
                        val = _get_by_path(cfg, path)
                        missing = val is None or (isinstance(val, str) and not val.strip())
                        if missing:
                            req(path, "Required field is missing for selected variant.")

    required_secrets: list[str] = []
    rs = manifest.get("requiredSecrets")
    if isinstance(rs, list):
        required_secrets = [str(x) for x in rs if isinstance(x, str) and x.strip()]
    elif isinstance(rs, dict):
        if "allOf" in rs and isinstance(rs.get("allOf"), list):
            seen: set[str] = set()
            out: list[str] = []
            for clause in rs.get("allOf") or []:
                if not clause:
                    continue
                clause_manifest = dict(manifest)
                clause_manifest["requiredSecrets"] = clause
                sub = validate_connection_config(clause_manifest, cfg).required_secrets
                for key in sub:
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(key)
            required_secrets = out
        else:
            dp = rs.get("discriminatorPath")
            variants = rs.get("variants")
            if isinstance(dp, str) and isinstance(variants, dict):
                disc = _get_by_path(cfg, dp)
                if isinstance(disc, str) and disc in variants and isinstance(variants[disc], list):
                    required_secrets = [str(x) for x in variants[disc] if isinstance(x, str) and x.strip()]

    return ValidationResult(ok=not errors, config=cfg, required_secrets=required_secrets, errors=errors)
