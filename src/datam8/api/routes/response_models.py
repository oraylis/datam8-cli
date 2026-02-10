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

from pydantic import BaseModel, ConfigDict, Field


class AnyPayloadResponse(BaseModel):
    """Flexible typed response for payloads with route-specific keys."""

    model_config = ConfigDict(extra="allow")


class ConfigResponse(BaseModel):
    """Current backend runtime mode."""

    mode: str


class VersionResponse(BaseModel):
    """Version payload."""

    version: str


class SolutionResponse(BaseModel):
    """Solution and resolved path metadata."""

    solution: dict[str, Any]
    resolvedPaths: dict[str, str]


class SolutionFullResponse(BaseModel):
    """Solution and full entity contents."""

    solution: dict[str, Any]
    baseEntities: list[dict[str, Any]]
    modelEntities: list[dict[str, Any]]


class SolutionPathResponse(BaseModel):
    """Path response for created projects."""

    solutionPath: str


class CountEntitiesResponse(BaseModel):
    """Counted list response for entities."""

    count: int
    entities: list[dict[str, Any]]


class MessageWithPathResponse(BaseModel):
    """Standard mutation response with path payload."""

    message: str
    absPath: str


class EntriesResponse(BaseModel):
    """Filesystem listing response."""

    entries: list[dict[str, Any]]


class ContentResponse(BaseModel):
    """Text content response."""

    content: str


class ScriptListResponse(BaseModel):
    """List of scripts."""

    count: int
    scripts: list[Any]


class ConnectorsResponse(BaseModel):
    """Connector summaries."""

    connectors: list[dict[str, Any]]


class ConnectorSchemaResponse(BaseModel):
    """Connector UI schema payload."""

    connectorId: str
    version: str
    schema_: dict[str, Any] = Field(alias="schema")


class TablesResponse(BaseModel):
    """Datasource table list payload."""

    tables: list[dict[str, Any]]


class MetadataResponse(BaseModel):
    """Datasource metadata payload."""

    metadata: dict[str, Any]


class UsagesResponse(BaseModel):
    """Datasource usage payload."""

    usages: list[dict[str, Any]]


class DiffsResponse(BaseModel):
    """Schema refresh preview payload."""

    diffs: list[dict[str, Any]]


class UpdatedEntitiesResponse(BaseModel):
    """Schema refresh apply payload."""

    updatedEntities: list[dict[str, Any]]


class RuntimeSecretsResponse(BaseModel):
    """Runtime secret reference payload."""

    runtimeSecrets: dict[str, str] | None


class AvailableResponse(BaseModel):
    """Boolean capability response."""

    available: bool
