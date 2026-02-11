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

from fastapi import APIRouter
from pydantic import BaseModel

from datam8.core.version import get_version

router = APIRouter()


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: str


class VersionResponse(BaseModel):
    """Version endpoint response."""

    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok")


@router.get("/version")
async def version() -> VersionResponse:
    """Return backend version."""
    return VersionResponse(version=get_version())

