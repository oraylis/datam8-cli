from __future__ import annotations

import copy
from typing import Any

from datam8.core.errors import Datam8ValidationError


def parse_json_pointer(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise Datam8ValidationError(
            message="Invalid JSON pointer. Expected e.g. /a/b/0",
            details={"pointer": pointer},
        )
    parts = pointer.split("/")[1:]
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]


def set_by_pointer(doc: Any, pointer: str, value: Any, *, create_missing: bool = True) -> Any:
    parts = parse_json_pointer(pointer)
    if not parts:
        return value

    cur = doc
    for i, part in enumerate(parts[:-1]):
        next_part = parts[i + 1]
        if isinstance(cur, dict):
            if part not in cur:
                if not create_missing:
                    raise Datam8ValidationError(message="Path does not exist.", details={"pointer": pointer})
                cur[part] = [] if _looks_like_index(next_part) else {}
            cur = cur[part]
            continue
        if isinstance(cur, list):
            idx = _parse_index(part, pointer)
            if idx >= len(cur):
                if not create_missing:
                    raise Datam8ValidationError(message="Path does not exist.", details={"pointer": pointer})
                while len(cur) <= idx:
                    cur.append(None)
            if cur[idx] is None:
                cur[idx] = [] if _looks_like_index(next_part) else {}
            cur = cur[idx]
            continue
        raise Datam8ValidationError(message="Path does not exist.", details={"pointer": pointer})

    last = parts[-1]
    if isinstance(cur, dict):
        cur[last] = value
        return doc
    if isinstance(cur, list):
        idx = _parse_index(last, pointer)
        if idx > len(cur):
            raise Datam8ValidationError(message="List index out of range.", details={"pointer": pointer})
        if idx == len(cur):
            cur.append(value)
        else:
            cur[idx] = value
        return doc
    raise Datam8ValidationError(message="Path does not exist.", details={"pointer": pointer})


def merge_patch(target: Any, patch: Any) -> Any:
    # RFC 7396 (subset): objects are merged; non-objects replace; null deletes.
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    if not isinstance(target, dict):
        target = {}
    result = dict(target)
    for k, v in patch.items():
        if v is None:
            result.pop(k, None)
            continue
        if isinstance(v, dict):
            result[k] = merge_patch(result.get(k), v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def _looks_like_index(part: str) -> bool:
    try:
        int(part)
        return True
    except Exception:
        return False


def _parse_index(part: str, pointer: str) -> int:
    try:
        idx = int(part)
    except Exception:
        raise Datam8ValidationError(message="Expected list index in JSON pointer.", details={"pointer": pointer})
    if idx < 0:
        raise Datam8ValidationError(message="Negative list index in JSON pointer.", details={"pointer": pointer})
    return idx

