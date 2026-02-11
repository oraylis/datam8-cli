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

