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

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from datam8.core.connectors import plugin_manager
from datam8.core.parse_utils import parse_duration_seconds


class OperationWithMessagesError(Exception):
    """Wrap an operation error together with captured backend log messages."""

    def __init__(self, original: Exception, messages: list[str]) -> None:
        super().__init__(str(original))
        self.original = original
        self.messages = messages


class _ThreadLogCaptureHandler(logging.Handler):
    def __init__(self, *, sink: list[str]) -> None:
        super().__init__(level=logging.NOTSET)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        if not (record.name.startswith("datam8") or record.name.startswith("datam8_model")):
            return
        msg = record.getMessage()
        if msg:
            level = (record.levelname or "INFO").upper()
            self._sink.append(f"[{level}] {record.name} | {msg}")


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


def run_with_log_messages[T](func: Callable[[], T]) -> tuple[T, list[str]]:
    """Execute a callable and capture datam8 log lines emitted during the run."""
    messages: list[str] = []
    handler = _ThreadLogCaptureHandler(sink=messages)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        return func(), messages
    except Exception as err:
        raise OperationWithMessagesError(err, messages) from err
    finally:
        root_logger.removeHandler(handler)
