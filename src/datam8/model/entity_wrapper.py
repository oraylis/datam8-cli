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
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, ValidationError

from datam8 import logging, utils
from datam8 import model_exceptions as errors
from datam8_model import attribute as a
from datam8_model import base as b
from datam8_model import data_product as dp
from datam8_model import data_source as ds
from datam8_model import data_type as dt
from datam8_model import folder as f
from datam8_model import model as m
from datam8_model import property as p
from datam8_model import zone as z

from .locator import Locator

logger = logging.getLogger(__name__)

type BaseEntityDict[T: b.BaseEntityType] = dict[b.EntityType, list[T]]
type EntityDict[T: b.BaseEntityType] = dict[Locator, EntityWrapper[T]]


class PropertyReference(p.PropertyReference):
    """
    Sub-class of `datam8.property.PropertyReference` for actual use with the
    generator offering further functionality.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, p.PropertyReference):
            return self.property == other.property and self.value == other.value
        elif not isinstance(other, PropertyReference):
            return False

        return self.property == other.property and self.value == other.value

    def __hash__(self):
        return hash((self.property, self.value))

    @staticmethod
    def from_model_ref(ref: p.PropertyReference):
        """
        Converts a PropertyReference parsed from a json file into the
        internally used one.

        # Parameters
        ----------
        ref : `datam8_model.property.PropertyReference`
            Reference to a property value, directly parsed from the json files.
        """
        return PropertyReference(
            property=ref.property,
            value=ref.value,
        )


class EntityWrapper[T: b.BaseEntityType](BaseModel):
    """
    A wrapper class around the actual solution files offering more information
    and functionality for further use of the model.

    This class should be used everywhere within the generator. The underlying
    obejcts parsed from the jso files should mostly not handled directly and
    seen only as data.
    Functionality will be implemented mostly on this wrapper.

    Attributes
    ----------
    locator : `Locator`
    entity : `T`, generic
    resolved : `bool`
    properties : `dict[PropertyReference, EntityWrapper[PropertyValue]]`
    """

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    locator: Locator
    """
    A unique identifier for every entity/object within the solution.
    """
    source_file: Path
    """
    The path to the model file where this entity is stored in.
    """
    entity: T
    """
    The actual entity description read from the datam8 solution, e.g. DataSource
    or ModelEntity.
    """
    resolved: bool = False
    """
    Marks if references to other entities, e.g. Properties have  been resolved.
    """
    _properties: dict[Locator, p.PropertyValue] = {}
    "Use `properties` instead when accessing them. This is meant for internal generator usage."
    _changed: bool = False
    "Flag to track if the wrapped entity has been changed"
    _deleted: bool = False
    "Flag to track if the wrapped entity has been deleted"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntityWrapper):
            return False

        return self.locator == other.locator

    @property
    def has_changed(self) -> bool:
        return self._changed

    @property
    def is_deleted(self) -> bool:
        return self._deleted

    @property
    def properties(self) -> dict[Locator, p.PropertyValue]:
        """
        Additional properties than are dynamically defined within the solution.
        Contains actual properties based on the property references with the
        `entity.properties` attribute.

        Raises
        ------
        PropertiesNotResolvedError
            If the property references within the entity have not been resolved yet.
        """
        if not self.resolved:
            raise errors.PropertiesNotResolvedError(self.locator)

        return self._properties

    def reset(self, locator: Locator, source_file: Path | None = None) -> None:
        self.locator = locator
        self._properties = {}
        self.resolved = False
        self._changed = False
        self._deleted = False
        self.source_file = source_file or self.source_file

    def has_property(self, property_name: str) -> bool:
        """
        Indicates if this entity has a given property assigned.

        Parameters
        ----------
        propert_name : `str`
            The property name to check if assigned.

        Returns
        -------
        bool
            If true the property name is assigned.
        """
        for pr in self.properties:
            if self.properties[pr].property == property_name:
                return True

        return False

    def _resolve_model_attributes(self, model: "Model") -> None:
        if not isinstance(self.entity, m.ModelEntity):
            return

        for attr in self.entity.attributes:
            pass
            # logger.error(attr.properties)

    def get_inherited_property_references(self, model: "Model") -> list[p.PropertyReference]:
        """
        Get a distinct list of properties of parent Entities (most likely foldres).

        Returns
        -------
        list[PropertyReference]
            A list of PropertyReference of parent locators. They are not yet resolved recursivley.
        """
        parent_properties: list[p.PropertyReference] = []

        for parent in self.locator.parents:
            if parent not in model.folders:
                continue

            parent_folder = model.folders[parent].entity

            if not parent_folder.properties:
                continue

            parent_properties.extend(
                iter([pr for pr in parent_folder.properties if pr not in parent_properties])
            )

        return parent_properties

    def _resolve_properties(
        self, model: "Model", properties: Sequence[p.PropertyReference]
    ) -> None:
        """
        Recursivly resolve properties assigned to this entity, directly or indirectly via
        folders.

        Parent property references are currently only being resolved for modelEntities.

        Parameters
        ----------
        model : `model.model`
            The DataM8 model to lookup up the property values. This normally is the same
            model as the one this EntityWrapper resides in, but could technically be a
            sperate model.
        properties : `Sequence[PropertyReference]`
            PropertyReferences that should be looked up recursively.
        """
        if len(properties) == 0:
            return

        converted_properties = [PropertyReference.from_model_ref(pr) for pr in properties]

        logger.debug(
            "%s - %s",
            self.locator,
            [f"{p.property}:{p.value}" for p in converted_properties],
        )

        for ref in converted_properties:
            property_value = model.get_property_value(ref.property, ref.value)
            self._properties[property_value.locator] = property_value.entity

            # NOTE: break recursion
            if property_value.entity.properties:
                self._resolve_properties(model, property_value.entity.properties)

    def update(self, **kwargs: Any) -> None:
        new_entity = self.entity.model_copy(update=kwargs, deep=True)

        try:
            new_entity = type(new_entity).model_validate(new_entity)
        except ValidationError as err:
            raise utils.create_error(err, code=520)

        self.entity = new_entity
        self._changed = True


EntityWrapperVariant: TypeAlias = (  # noqa: UP040
    EntityWrapper[a.AttributeType]
    | EntityWrapper[dp.DataProduct]
    | EntityWrapper[dp.DataModule]
    | EntityWrapper[ds.DataSource]
    | EntityWrapper[ds.DataSourceType]
    | EntityWrapper[dt.DataTypeDefinition]
    | EntityWrapper[f.Folder]
    | EntityWrapper[m.ModelEntity]
    | EntityWrapper[p.Property]
    | EntityWrapper[p.PropertyValue]
    | EntityWrapper[z.Zone]
)
