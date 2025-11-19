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

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from . import attribute, data_type, property


class Locator(BaseModel):
    """
    Describes an abstract way to point to and find entities with datam8.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    entityType: str
    folders: list[str]
    """
    Hierarchical list of olders under the base-/modelpath. Order is relevant.
    """
    entityName: str | None = None
    """
    Name property of the entity object.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> Locator:
        return Locator.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> Locator:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        Locator
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = Locator.model_validate_json(file.read())

        return model


class ModelParameter(BaseModel):
    """
    Key-Value pair parameters for customization of and entity-level attributes.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    name: str
    value: str | Mapping[str, Any] | float | bool

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ModelParameter:
        return ModelParameter.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ModelParameter:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ModelParameter
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ModelParameter.model_validate_json(file.read())

        return model


class TransformationKind(Enum):
    """
    Type of transformation, either `builtin` or `function`.
    """

    BUILTIN = "builtin"
    FUNCTION = "function"


class TransformationFunction(BaseModel):
    """
    A transformation function defined in the scope of the current solution.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source: str

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> TransformationFunction:
        return TransformationFunction.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> TransformationFunction:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        TransformationFunction
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = TransformationFunction.model_validate_json(file.read())

        return model


class ModelAttributeMapping(BaseModel):
    """
    Single attribute mapping.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    sourceName: Annotated[str, Field(min_length=1)]
    targetName: Annotated[str, Field(min_length=1)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ModelAttributeMapping:
        return ModelAttributeMapping.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ModelAttributeMapping:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ModelAttributeMapping
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ModelAttributeMapping.model_validate_json(file.read())

        return model


class SourceAttributeMapping(ModelAttributeMapping):
    """
    Map an attribute in the source to one in the current entity. May optionally contain an explicit source data type.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    sourceDataType: data_type.DataType | None = None
    properties: Sequence[property.PropertyReference] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> SourceAttributeMapping:
        return SourceAttributeMapping.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> SourceAttributeMapping:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        SourceAttributeMapping
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = SourceAttributeMapping.model_validate_json(file.read())

        return model


class ModelTransformation(BaseModel):
    """
    Describes a single transformation, either builtin or defined within the solution.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    stepNo: Annotated[int, Field(ge=1)]
    kind: Annotated[TransformationKind, Field(title="TransformationKind")]
    """
    Type of transformation, either `builtin` or `function`.
    """
    name: str
    properties: Sequence[property.PropertyReference] | None = None
    function: Annotated[
        TransformationFunction | None, Field(title="TransformationFunction")
    ] = None
    """
    A transformation function defined in the scope of the current solution.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ModelTransformation:
        return ModelTransformation.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ModelTransformation:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ModelTransformation
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ModelTransformation.model_validate_json(file.read())

        return model


class ModelRelationship(BaseModel):
    """
    Maps attributes to a target location.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    targetLocation: int
    attributes: Annotated[Sequence[ModelAttributeMapping], Field(min_length=1)]

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ModelRelationship:
        return ModelRelationship.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ModelRelationship:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ModelRelationship
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ModelRelationship.model_validate_json(file.read())

        return model


class InternalModelSource(BaseModel):
    """
    Internal source definition to reference other entities within datam8.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    sourceLocation: str | int
    properties: Sequence[property.PropertyReference] | None = None
    mapping: Sequence[SourceAttributeMapping] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> InternalModelSource:
        return InternalModelSource.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> InternalModelSource:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        InternalModelSource
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = InternalModelSource.model_validate_json(file.read())

        return model


class ExternalModelSource(BaseModel):
    """
    Sources that point to external systems outside of datam8.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    dataSource: str
    sourceAlias: str | None = None
    sourceLocation: str
    properties: Sequence[property.PropertyReference] | None = None
    mapping: Sequence[SourceAttributeMapping] | None = None

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ExternalModelSource:
        return ExternalModelSource.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ExternalModelSource:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ExternalModelSource
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ExternalModelSource.model_validate_json(file.read())

        return model


class ModelEntity(BaseModel):
    """
    Describes a single entity within datam8. Most commonly a database table.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: Annotated[int, Field(gt=0)]
    """
    Internal id of an entity.
    """
    name: str
    displayName: str | None = None
    description: str | None = None
    parameters: Sequence[ModelParameter] | None = None
    attributes: Annotated[Sequence[attribute.Attribute], Field(min_length=1)]
    properties: Sequence[property.PropertyReference] | None = None
    sources: Sequence[InternalModelSource | ExternalModelSource]
    transformations: Sequence[ModelTransformation]
    """
    List of transformations that will be executed in order of stepNo.
    """
    relationships: Sequence[ModelRelationship]
    """
    List of entity relationships.
    """

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")

    @staticmethod
    def from_dict(obj) -> ModelEntity:
        return ModelEntity.model_validate(obj, from_attributes=False)

    @staticmethod
    def from_json_file(path: Path) -> ModelEntity:
        """Loads ands validates a json file from the given path.

        Parameters
        ----------
        path : Path
          The path to the json to be loaded into the model.

        Returns
        -------
        ModelEntity
            Instantiated and validated pydantic model

        Raises
        ------
        ValidationError
            If the data in the json file does not much the model constraints.
        """
        with open(path) as file:
            model = ModelEntity.model_validate_json(file.read())

        return model
