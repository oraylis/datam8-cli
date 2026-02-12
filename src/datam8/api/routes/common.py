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

import os
from pathlib import Path
from typing import Any

from datam8.core.connectors import plugin_manager
from datam8.core.parse_utils import parse_duration_seconds


def plugin_dir() -> Path:
    """Resolve the connector plugin directory from env or default location."""
    configured = os.environ.get("DATAM8_PLUGIN_DIR")
    if configured and configured.strip():
        return Path(configured)
    return plugin_manager.default_plugin_dir()


def lock_timeout_seconds(body: Any) -> float:
    """Parse lock timeout from request body with a safe default."""
    try:
        value = body.get("lockTimeout")
        if isinstance(value, str) and value.strip():
            return parse_duration_seconds(value)
    except Exception:
        pass
    return parse_duration_seconds("10s")
