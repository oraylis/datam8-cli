from __future__ import annotations

import re

from datam8.core.errors import Datam8ValidationError

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def parse_duration_seconds(value: str) -> float:
    """
    Parse durations like '10s', '2m', '1h', '1d' into seconds.
    """
    if not isinstance(value, str) or not value.strip():
        raise Datam8ValidationError(code="validation_error", message="Invalid duration.", details={"value": value})
    m = _DURATION_RE.match(value)
    if not m:
        raise Datam8ValidationError(
            code="validation_error",
            message="Invalid duration format. Use e.g. 10s, 2m, 1h, 1d.",
            details={"value": value},
        )
    amount = int(m.group(1))
    unit = m.group(2).lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return float(amount * mult)

