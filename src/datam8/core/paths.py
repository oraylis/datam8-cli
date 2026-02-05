from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError


@dataclass(frozen=True)
class ResolvedSolution:
    solution_file: Path
    root_dir: Path


def resolve_solution(candidate: Optional[str]) -> ResolvedSolution:
    if not candidate:
        raise Datam8ValidationError(
            message="No solution specified. Use --solution or set DATAM8_SOLUTION_PATH.",
            details=None,
        )

    p = Path(candidate).expanduser()
    if p.is_dir():
        dm8s = sorted(p.glob("*.dm8s"))
        if not dm8s:
            raise Datam8NotFoundError(message="No .dm8s file found in the provided directory.", details={"dir": str(p)})
        if len(dm8s) > 1:
            raise Datam8ValidationError(
                message="Multiple .dm8s files found; provide an explicit .dm8s path.",
                details={"dir": str(p), "candidates": [str(x) for x in dm8s]},
            )
        solution_file = dm8s[0]
    else:
        if p.suffix.lower() != ".dm8s":
            raise Datam8ValidationError(
                message="--solution must be a .dm8s file or a folder containing exactly one .dm8s file.",
                details={"solution": str(p)},
            )
        if not p.exists():
            raise Datam8NotFoundError(message="Solution file not found.", details={"solution": str(p)})
        solution_file = p

    try:
        root = solution_file.parent.resolve(strict=True)
        solution_file = solution_file.resolve(strict=True)
    except FileNotFoundError:
        raise Datam8NotFoundError(message="Solution file not found.", details={"solution": str(solution_file)})

    return ResolvedSolution(solution_file=solution_file, root_dir=root)


def safe_join(root_dir: Path, rel_path: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise Datam8ValidationError(message="Invalid path.", details={"relPath": rel_path})

    if "\0" in rel_path:
        raise Datam8ValidationError(message="Invalid path.", details={"relPath": rel_path})

    # Must be relative.
    if rel_path.startswith(("/", "\\")):
        raise Datam8ValidationError(message="Path must be relative to the solution root.", details={"relPath": rel_path})

    # Normalize separators.
    normalized = rel_path.replace("\\", "/")

    # Disallow absolute / drive-prefixed paths.
    if Path(normalized).is_absolute() or (len(normalized) >= 2 and normalized[1] == ":"):
        raise Datam8ValidationError(message="Path must be relative to the solution root.", details={"relPath": rel_path})

    parts = [p for p in normalized.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise Datam8ValidationError(message="Path must not contain '.' or '..'.", details={"relPath": rel_path})

    abs_path = (root_dir / Path(*parts)).resolve()
    root_resolved = root_dir.resolve()
    if not abs_path.is_relative_to(root_resolved):
        raise Datam8ValidationError(message="Path escapes the solution root.", details={"relPath": rel_path})
    return abs_path
