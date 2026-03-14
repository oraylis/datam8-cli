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

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Capability(Enum):
    """
    Available capabilities plugins can implement
    """

    UI_SCHEMA = "uiSchema"
    VALIDATION_CONNECTION = "validationConnection"
    METADATA = "metadata"


class PluginType(Enum):
    """
    Available types of plugins
    """

    CONNECTOR = "connector"


class PluginManifest(BaseModel):
    """
    A DataM8 plugin that e.g. provides additional ways to connect to source systems
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        revalidate_instances="always",
    )
    id: str
    displayName: str | None = None
    """
    Human-readable display name
    """
    version: str
    type: PluginType
    entryPoint: str
    """
    Python entrypoint that will be imported as a class of plugin
    """
    capabilities: Sequence[Capability]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj: Any) -> PluginManifest:
        return PluginManifest.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> PluginManifest:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        PluginManifest
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = PluginManifest.model_validate_json(file.read())

        return model

    def to_json_file(self, path: Path, mode: str, dump_options: dict[str, Any]) -> None:
        with open(path, mode) as file:
            file.write(self.model_dump_json(**dump_options))
