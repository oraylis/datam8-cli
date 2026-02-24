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
from pathlib import Path

from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError


@dataclass(frozen=True)
class ResolvedSolution:
    solution_file: Path
    root_dir: Path


def resolve_solution(candidate: str | None) -> ResolvedSolution:
    """Resolve a solution candidate to root directory and `.dm8s` file.

    Parameters
    ----------
    candidate : str | None
        File or folder path, or `None` to trigger validation error.

    Returns
    -------
    ResolvedSolution
        Resolved solution metadata (`root_dir`, `solution_file`).

    Raises
    ------
    Datam8NotFoundError
        If candidate path does not exist or folder has no single `.dm8s`.
    Datam8ValidationError
        If no solution candidate is provided."""
    if not candidate:
        raise Datam8ValidationError(
            message="No solution specified. Use --solution/-s (or --solution-path) or set DATAM8_SOLUTION_PATH.",
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
                message="--solution/--solution-path must be a .dm8s file or a folder containing exactly one .dm8s file.",
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
    """Join `root_dir` with a relative path and enforce root confinement.

    Parameters
    ----------
    root_dir : Path
        Trusted solution root directory.
    rel_path : str
        Relative path to resolve under `root_dir`.

    Returns
    -------
    Path
        Absolute normalized path.

    Raises
    ------
    Datam8ValidationError
        If `rel_path` escapes `root_dir`."""
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
