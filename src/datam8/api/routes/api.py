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

from datam8.api.routes.api_connectors import router as connectors_router
from datam8.api.routes.api_solution import router as solution_router
from datam8.api.routes.api_workspace import router as workspace_router

router = APIRouter()
router.include_router(solution_router)
router.include_router(workspace_router)
router.include_router(connectors_router)
