from __future__ import annotations

import json
from typing import Any

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError
from datam8.core.paths import safe_join
from datam8.core.workspace_io import read_solution


def read_index(solution_path: str | None) -> dict[str, Any]:
    resolved, _sol = read_solution(solution_path)
    idx = resolved.root_dir / "index.json"
    if not idx.exists():
        raise Datam8NotFoundError(message="index.json not found.", details={"path": str(idx)})
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except Exception as e:
        raise Datam8ValidationError(message="Invalid index.json.", details={"error": str(e)})
    if not isinstance(data, dict):
        raise Datam8ValidationError(message="Invalid index.json shape.", details=None)
    return data


def validate_index(solution_path: str | None) -> dict[str, Any]:
    resolved, _sol = read_solution(solution_path)
    root = resolved.root_dir
    data = read_index(solution_path)

    locators: dict[str, str] = {}
    duplicates: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    checked = 0

    for key, block in data.items():
        if not isinstance(block, dict):
            continue
        entries = block.get("entry")
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            locator = e.get("locator")
            name = e.get("name")
            abs_path = e.get("absPath")
            if not isinstance(locator, str) or not isinstance(name, str) or not isinstance(abs_path, str):
                continue
            checked += 1
            if locator in locators:
                duplicates.append({"locator": locator, "first": locators[locator], "second": abs_path})
            else:
                locators[locator] = abs_path

            rel = _rel_from_locator(locator)
            if rel:
                target = safe_join(root, rel)
                if not target.exists():
                    missing.append({"locator": locator, "expectedRelPath": rel})

    return {"ok": not duplicates and not missing, "checked": checked, "missing": missing, "duplicates": duplicates}


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

