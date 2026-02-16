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

from pydantic import BaseModel

from datam8.core.locator_codec import locator_to_string
from datam8.core.solution_index import iter_solution_json_files
from datam8.core.workspace_io import list_model_entities


class TextMatch(BaseModel):
    """Single file match summary for text search."""

    file: str
    count: int


def search_entities(*, solution_path: str | None, query: str) -> dict[str, Any]:
    """Search model entities by name, locator, and relative path.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    query : str
        Case-insensitive search term.

    Returns
    -------
    dict[str, Any]
        Match summary with `count` and matched entity payloads."""
    q = (query or "").strip().lower()
    entities = list_model_entities(solution_path)
    matches = []
    for e in entities:
        locator_str = locator_to_string(e.locator).lower()
        if q in (e.name or "").lower() or q in locator_str or q in (e.relPath or "").lower():
            matches.append(e.model_dump())
    return {"count": len(matches), "entities": matches}


def search_text(*, solution_path: str | None, pattern: str) -> dict[str, Any]:
    """Search raw text occurrences across solution JSON files.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.
    pattern : str
        Literal text pattern to count.

    Returns
    -------
    dict[str, Any]
        Search summary with matched files and total occurrence count."""
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
    return {"count": len(results), "total": total, "matches": [r.model_dump() for r in results]}

