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

from typing import Any

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    """Stable JSON envelope for API error responses."""

    code: str
    message: str
    details: Any = None
    hint: str | None = None
    traceId: str | None = None


class Datam8Error(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Any = None,
        hint: str | None = None,
        exit_code: int = 10,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.hint = hint
        self.exit_code = exit_code

    def to_envelope(self, *, trace_id: str | None = None) -> ErrorEnvelope:
        return ErrorEnvelope(code=self.code, message=self.message, details=self.details, hint=self.hint, traceId=trace_id)


class Datam8ValidationError(Datam8Error):
    def __init__(self, *, code: str = "validation_error", message: str, details: Any = None, hint: str | None = None):
        super().__init__(code=code, message=message, details=details, hint=hint, exit_code=2)


class Datam8NotFoundError(Datam8Error):
    def __init__(self, *, code: str = "not_found", message: str, details: Any = None, hint: str | None = None):
        super().__init__(code=code, message=message, details=details, hint=hint, exit_code=3)


class Datam8ConflictError(Datam8Error):
    def __init__(self, *, code: str = "conflict", message: str, details: Any = None, hint: str | None = None):
        super().__init__(code=code, message=message, details=details, hint=hint, exit_code=4)


class Datam8ExternalSystemError(Datam8Error):
    def __init__(self, *, code: str = "external_error", message: str, details: Any = None, hint: str | None = None):
        super().__init__(code=code, message=message, details=details, hint=hint, exit_code=5)


class Datam8PermissionError(Datam8Error):
    def __init__(self, *, code: str = "permission", message: str, details: Any = None, hint: str | None = None):
        super().__init__(code=code, message=message, details=details, hint=hint, exit_code=6)


class Datam8NotImplementedError(Datam8Error):
    def __init__(self, *, message: str = "Not implemented.", details: Any = None, hint: str | None = None):
        super().__init__(code="not_implemented", message=message, details=details, hint=hint, exit_code=5)


def as_datam8_error(err: Exception) -> Datam8Error:
    """As datam8 error.

    Parameters
    ----------
    err : Exception
        err parameter value.

    Returns
    -------
    Datam8Error
        Computed return value."""
    if isinstance(err, Datam8Error):
        return err
    return Datam8Error(code="unexpected", message=str(err) or "Unexpected error.", details=None, hint=None, exit_code=10)

