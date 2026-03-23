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

from typing import Any

from fastapi import APIRouter

from datam8 import factory
from datam8_model import plugin as pl

plugins_router = APIRouter(prefix="/plugins")


@plugins_router.get("/")
async def get_plugins() -> list[pl.PluginManifest]:
    return factory.get_plugin_manager().get_plugins()


@plugins_router.get("/reload")
async def reload_olugins() -> list[pl.PluginManifest]:
    return factory.get_plugin_manager().reload(factory.get_model().solution)


@plugins_router.get("/{plugin_id}")
async def get_plugin(plugin_id: str) -> pl.PluginManifest:
    return factory.get_plugin_manager().get_plugin_manifest(plugin_id)


@plugins_router.get("/{plugin_id}/ui-schema")
async def get_plugin_ui_schema(plugin_id: str) -> dict[str, Any]:
    return factory.get_plugin_manager().get_plugin(plugin_id).get_ui_schema()
