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

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.core.paths import safe_join
from datam8.core.workspace_io import read_solution


def iter_solution_json_files(solution_path: str | None) -> Iterator[Path]:
    """Iterate all JSON files that belong to the active solution."""
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir

    for rel_dir in [sol.basePath, sol.modelPath]:
        base = (root / rel_dir).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for path in base.rglob("*.json"):
            try:
                resolved_path = path.resolve(strict=True)
            except FileNotFoundError:
                continue
            if resolved_path.is_file():
                yield resolved_path

    index_path = root / "index.json"
    if index_path.exists() and index_path.is_file():
        yield index_path.resolve()


def detect_solution_version(path: str) -> str:
    """Detect whether a solution file/folder is v1 or v2."""
    target_path = Path(path)
    if target_path.is_dir():
        dm8s = sorted(target_path.glob("*.dm8s"))
        if len(dm8s) != 1:
            raise Datam8ValidationError(
                message="Path must be a .dm8s file or a folder containing exactly one .dm8s file."
            )
        target_path = dm8s[0]
    if not target_path.exists():
        raise Datam8ValidationError(message="Solution path not found.")
    try:
        raw = target_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise Datam8ValidationError(
            message="Invalid solution file.",
            details={"error": str(exc)},
        )
    return "v2" if isinstance(data, dict) and "schemaVersion" in data else "v1"


def read_index(solution_path: str | None) -> dict[str, Any]:
    """Read index.json from the active solution root."""
    resolved, _sol = read_solution(solution_path)
    index_path = resolved.root_dir / "index.json"
    if not index_path.exists():
        raise Datam8NotFoundError(
            message="index.json not found.",
            details={"path": str(index_path)},
        )
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise Datam8ValidationError(
            message="Invalid index.json.",
            details={"error": str(exc)},
        )
    if not isinstance(data, dict):
        raise Datam8ValidationError(message="Invalid index.json shape.", details=None)
    return data


def validate_index(solution_path: str | None) -> dict[str, Any]:
    """Validate index locators and duplicate entries."""
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    data = read_index(solution_path)

    locators: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    checked = 0

    for _key, block in data.items():
        if not isinstance(block, dict):
            continue
        entries = block.get("entry")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            locator = entry.get("locator")
            name = entry.get("name")
            abs_path = entry.get("absPath")
            if not isinstance(locator, str) or not isinstance(name, str) or not isinstance(abs_path, str):
                continue
            checked += 1
            if locator in locators:
                duplicates.append(
                    {"locator": locator, "first": locators[locator], "second": abs_path}
                )
            else:
                locators[locator] = abs_path

            rel = _rel_from_locator(locator)
            if rel:
                target = safe_join(root, rel)
                if not target.exists():
                    missing.append({"locator": locator, "expectedRelPath": rel})

    return {
        "ok": not duplicates and not missing,
        "checked": checked,
        "missing": missing,
        "duplicates": duplicates,
    }


def _rel_from_locator(locator: str) -> str | None:
    loc = (locator or "").strip()
    if not loc.startswith("/"):
        return None
    pathish = loc.lstrip("/")
    if not pathish:
        return None
    if pathish.lower().endswith(".json"):
        return pathish
    return pathish + ".json"
