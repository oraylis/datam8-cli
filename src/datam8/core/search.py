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

