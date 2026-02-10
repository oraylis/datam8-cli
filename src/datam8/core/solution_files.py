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

from datam8.core.errors import Datam8ValidationError
from datam8.core.workspace_io import read_solution


def iter_solution_json_files(solution_path: str | None) -> Iterator[Path]:
    """Iterate all JSON files that belong to the active solution.

    Parameters
    ----------
    solution_path : str | None
        Optional explicit solution path.

    Returns
    -------
    Iterator[Path]
        Absolute paths for Base/Model JSON files and optional `index.json`."""
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
    """Detect whether a solution file/folder is v1 or v2.

    Parameters
    ----------
    path : str
        Path to a `.dm8s` file or a folder containing exactly one `.dm8s`.

    Returns
    -------
    str
        `"v2"` when `schemaVersion` is present, otherwise `"v1"`.

    Raises
    ------
    Datam8ValidationError
        If the path cannot be resolved to a valid solution JSON file."""
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
