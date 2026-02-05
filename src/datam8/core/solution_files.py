from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

from datam8.core.workspace_io import read_solution
from datam8.core.errors import Datam8ValidationError


def iter_solution_json_files(solution_path: Optional[str]) -> Iterator[Path]:
    resolved, sol = read_solution(solution_path)
    root = resolved.root_dir

    # Base + Model folders
    for rel_dir in [sol.basePath, sol.modelPath]:
        base = (root / rel_dir).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for p in base.rglob("*.json"):
            try:
                rp = p.resolve(strict=True)
            except FileNotFoundError:
                continue
            if rp.is_file():
                yield rp

    # Root index.json if present
    idx = root / "index.json"
    if idx.exists() and idx.is_file():
        yield idx.resolve()


def detect_solution_version(path: str) -> str:
    p = Path(path)
    if p.is_dir():
        dm8s = sorted(p.glob("*.dm8s"))
        if len(dm8s) != 1:
            raise Datam8ValidationError(message="Path must be a .dm8s file or a folder containing exactly one .dm8s file.")
        p = dm8s[0]
    if not p.exists():
        raise Datam8ValidationError(message="Solution path not found.")
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as e:
        raise Datam8ValidationError(message="Invalid solution file.", details={"error": str(e)})
    return "v2" if isinstance(data, dict) and "schemaVersion" in data else "v1"
