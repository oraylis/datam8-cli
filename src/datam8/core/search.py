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

from dataclasses import dataclass
from typing import Any

from datam8.core.solution_files import iter_solution_json_files
from datam8.core.workspace_io import list_model_entities


@dataclass(frozen=True)
class TextMatch:
    file: str
    count: int


def search_entities(*, solution_path: str | None, query: str) -> dict[str, Any]:
    q = (query or "").strip().lower()
    entities = list_model_entities(solution_path)
    matches = []
    for e in entities:
        if q in (e.name or "").lower() or q in (e.locator or "").lower() or q in (e.relPath or "").lower():
            matches.append(e.__dict__)
    return {"count": len(matches), "entities": matches}


def search_text(*, solution_path: str | None, pattern: str) -> dict[str, Any]:
    pat = pattern or ""
    if not pat:
        return {"count": 0, "matches": []}
    results: list[TextMatch] = []
    total = 0
    for p in iter_solution_json_files(solution_path):
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:
            continue
        c = raw.count(pat)
        if c:
            total += c
            results.append(TextMatch(file=str(p), count=c))
    return {"count": len(results), "total": total, "matches": [r.__dict__ for r in results]}

