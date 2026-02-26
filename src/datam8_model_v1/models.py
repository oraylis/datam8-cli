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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AreaTypes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Raw: str | None = None
    Stage: str | None = None
    Core: str | None = None
    Curated: str | None = None
    Diagram: str | None = None


class Solution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basePath: str
    rawPath: str | None = None
    stagingPath: str | None = None
    corePath: str | None = None
    curatedPath: str | None = None
    generatePath: str | None = None
    diagramPath: str | None = None
    outputPath: str | None = None
    areaTypes: AreaTypes | None = Field(default=None, alias="AreaTypes")


class AttributeTypeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    description: str | None = None
    defaultType: str | None = None
    defaultLength: int | None = None
    defaultPrecision: int | None = None
    defaultScale: int | None = None
    hasUnit: str | None = None
    isUnit: str | None = None
    canBeInRelation: bool | None = None
    isDefaultProperty: bool | None = None


class AttributeTypes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = None
    items: list[AttributeTypeItem] = Field(default_factory=list)


class DataModuleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None


class DataProductItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    module: list[DataModuleItem] = Field(default_factory=list)


class DataProducts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = None
    items: list[DataProductItem] = Field(default_factory=list)


class DataTypeMappingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceType: str
    targetType: str


class DataSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    type: str | None = None
    connectionString: str | None = None
    dataTypeMapping: list[DataTypeMappingItem] = Field(default_factory=list)
    extendedProperties: dict[str, str] | None = None


class DataSources(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = None
    items: list[DataSourceItem] = Field(default_factory=list)


class DataTypeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    description: str | None = None
    hasCharLen: bool | None = None
    hasPrecision: bool | None = None
    hasScale: bool | None = None
    parquetType: str | None = None
    sqlType: str | None = None


class DataTypes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = None
    items: list[DataTypeItem] = Field(default_factory=list)


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    value: Any | None = None
    custom: Any | None = None


class MappingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    sourceName: str | None = None
    sourceComputation: str | None = None
    source: str | None = None
    target: str | None = None


class RelationshipField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dm8lAttr: str | None = None
    dm8lKeyAttr: str | None = None


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dm8lKey: str | None = None
    role: str | None = None
    fields: list[RelationshipField] = Field(default_factory=list)


class Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    attributeType: str | None = None
    dataType: str | None = None
    type: str | None = None
    businessKeyNo: int | None = None
    tags: list[str] = Field(default_factory=list)
    parameter: list[Parameter] = Field(default_factory=list)
    refactorNames: list[str] = Field(default_factory=list)
    nullable: bool | None = None
    charLength: int | None = None
    charLen: int | None = None
    precision: int | None = None
    scale: int | None = None
    history: str | None = None
    dateModified: str | None = None


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataProduct: str | None = None
    dataModule: str | None = None
    name: str | None = None
    displayName: str | None = None
    purpose: str | None = None
    explanation: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    attribute: list[Attribute] = Field(default_factory=list)
    relationship: list[Relationship] = Field(default_factory=list)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dm8l: str | None = None
    mapping: list[MappingItem] = Field(default_factory=list)


class Function(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataSource: str | None = None
    sourceLocation: str | None = None
    source: list[Source] = Field(default_factory=list)
    attributeMapping: list[MappingItem] = Field(default_factory=list)
    name: str | None = None


class RawModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["raw"]
    entity: Entity | None = None
    function: Function | None = None


class StageModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["stage"]
    entity: Entity | None = None
    function: Function | None = None


class CoreModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["core"]
    entity: Entity | None = None
    function: Function | None = None


class CuratedModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["curated"]
    entity: Entity | None = None
    function: list[Function] = Field(default_factory=list)


type BaseEntitiesType = AttributeTypes | DataProducts | DataSources | DataTypes
type ModelEntitiesType = RawModelEntry | StageModelEntry | CoreModelEntry | CuratedModelEntry
