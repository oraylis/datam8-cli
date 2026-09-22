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

from fastapi import HTTPException, Response
from pydantic import BaseModel
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)


class Response204NoContent(Response):
    def __init__(self):
        super().__init__(status_code=HTTP_204_NO_CONTENT)


class Response404NotFound(HTTPException):
    def __init__(self, detail: Any):
        super().__init__(status_code=HTTP_404_NOT_FOUND, detail=detail)


class Response400BadRequest(HTTPException):
    def __init__(self, detail: Any):
        super().__init__(status_code=HTTP_400_BAD_REQUEST, detail=detail)


class Response409Conflict(HTTPException):
    def __init__(self, detail: Any):
        super().__init__(status_code=HTTP_409_CONFLICT, detail=detail)


class MultiItemResponse[T](BaseModel):
    count: int
    items: list[T]

    @classmethod
    def from_list[K](cls, items: list[K]) -> MultiItemResponse[K]:
        return MultiItemResponse(
            count=len(items),
            items=items,
        )


class SingleItemResponse[T](BaseModel):
    item: T
