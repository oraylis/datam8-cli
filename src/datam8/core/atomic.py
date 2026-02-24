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
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Atomic write bytes.

    Parameters
    ----------
    target : Path
        target parameter value.
    data : bytes
        data parameter value.

    Returns
    -------
    None
        Computed return value."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
        try:
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            # Best effort; not supported everywhere.
            pass
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def atomic_write_text(target: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomic write text.

    Parameters
    ----------
    target : Path
        target parameter value.
    text : str
        text parameter value.
    encoding : str
        encoding parameter value.

    Returns
    -------
    None
        Computed return value."""
    atomic_write_bytes(target, text.encode(encoding))


def atomic_write_json(target: Path, obj: Any, *, indent: int = 4) -> None:
    """Atomic write json.

    Parameters
    ----------
    target : Path
        target parameter value.
    obj : Any
        obj parameter value.
    indent : int
        indent parameter value.

    Returns
    -------
    None
        Computed return value."""
    text = json.dumps(obj, ensure_ascii=False, indent=indent) + "\n"
    atomic_write_text(target, text, encoding="utf-8")

