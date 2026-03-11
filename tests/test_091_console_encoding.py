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

from datam8 import utils


class _FakeStream:
    def __init__(self, *, encoding: str, is_tty: bool) -> None:
        self.encoding = encoding
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_spinner_disabled_in_electron_mode(monkeypatch) -> None:
    monkeypatch.setenv("DATAM8_MODE", "electron")
    monkeypatch.setattr(utils.sys, "stderr", _FakeStream(encoding="utf-8", is_tty=True))
    assert utils._can_render_progress_spinner() is False


def test_spinner_disabled_for_non_unicode_console(monkeypatch) -> None:
    monkeypatch.delenv("DATAM8_MODE", raising=False)
    monkeypatch.setattr(utils.sys, "stderr", _FakeStream(encoding="cp1252", is_tty=True))
    assert utils._can_render_progress_spinner() is False


def test_spinner_enabled_for_utf8_tty(monkeypatch) -> None:
    monkeypatch.delenv("DATAM8_MODE", raising=False)
    monkeypatch.setattr(utils.sys, "stderr", _FakeStream(encoding="utf-8", is_tty=True))
    assert utils._can_render_progress_spinner() is True
