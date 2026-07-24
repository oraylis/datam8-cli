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

import inspect
from collections.abc import Callable, Generator
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, ValidationError

from datam8 import errors, logging, utils
from datam8_model import attribute as a
from datam8_model import base as b
from datam8_model import data_product as dp
from datam8_model import data_source as ds
from datam8_model import data_type as dt
from datam8_model import folder as f
from datam8_model import model as m
from datam8_model import property as p
from datam8_model import zone as z

from .locator import Locator, LocatorOrString, _ensure_locator

logger = logging.getLogger(__name__)

type BaseEntityDict[T: b.BaseEntityType] = dict[b.EntityType, list[T]]
type EntityDict[T: b.BaseEntityType] = dict[Locator, EntityWrapper[T]]


def _ensure_string(locator: LocatorOrString) -> str:
    if isinstance(locator, str):
        return locator
    return locator.without_type()


class EntityRepository[T: b.BaseEntityType]:
    """
    `EntityRepository`

    Notes
    -----
    Prefer using locators for lookups since it will be faster

    Examples
    --------
    Create a repository by instantiating it with a dictionary of EntityWrappers

    >>> repository = EntityRepository[ModelEntity]({...})

    Use it retrieve entities. Most methods throw errors if the entity does not exist.

    >>> repository.get("Sales/Other/Order") # get entity by locator (with or without type)
    ... repository.get_by_name("Order") # get by name, will return the first found

    The repository supports common dictionary syntax.

    >>> wrapper = repository["modelEntities/Sales/Other/Order"]
    ... repository["modelEntities/Sales/Other/Order2"] = wrapper
    ... del repository["modelEntities/Sales/Other/Order2"]
    """

    def __init__(
        self,
        items: dict[Locator, EntityWrapper[T]] | None = None,
        /,
        entity_type: str | None = None,
        model: IModel | None = None,
    ) -> None:
        self.__entities: dict[Locator, EntityWrapper[T]] = items or {}
        "Internal dictionary containing a mapping of locators and wrappers"
        self.__entity_type: str | None = entity_type
        "An optional entity type that will be prefixed if a locator without an entity type is requested"
        self.__model: IModel | None = model
        "A DataM8 Model that allows to resolve EntityWrappers"
        self.lock = Lock()
        "Mutex"

    @property
    def model(self) -> IModel:
        assert self.__model is not None, "Model on repository must be set before usage"
        return self.__model

    @model.setter
    def model(self, val: IModel) -> None:
        assert self.__model is None, "Model on repository can only be set ones"
        self.__model = val

    def __ensure_locator(self, locator: LocatorOrString) -> Locator:
        match [locator, self.__entity_type]:
            case [Locator() as loc, _]:
                return loc
            case [str() as loc, str() as pre] if not loc.startswith(pre):
                return _ensure_locator(f"{pre}/{loc}")
            case [str() as loc, _]:
                return _ensure_locator(loc)
            case _:
                raise utils.create_error(
                    f"Invalid combination {locator}:{self.__entity_type}. This should not happen and indicates a bug"
                )

    def get(self, locator: LocatorOrString, /) -> EntityWrapper[T]:
        locator_ = self.__ensure_locator(locator)

        if locator_ not in self:
            raise utils.create_error(errors.EntityNotFoundError(entity=str(locator)))

        # TODO: this is kind of unsafe running without a lock, as in theorey an entity could get
        # deleted while resolving... but it is not possible to simply lock as this results in a
        # deadlock as multiple repositories can be depended on each other. Need some other solution
        # later on.
        if not self.__entities[locator_].resolved:
            return self.model.resolve_wrapper(self.__entities[locator_])
        else:
            return self.__entities[locator_]

    def get_where(self, filter_: Callable[[EntityWrapper[T]], bool], /) -> EntityWrapper[T]:
        wrappers = self.get_many_where(filter_)

        if len(wrappers) > 1:
            logger.error(inspect.getsource(filter_))
            raise utils.create_error("More than one entity found for filter.")

        if len(wrappers) < 1:
            logger.error(inspect.getsource(filter_))
            raise utils.create_error("No entity found for filter")

        return wrappers.pop()

    def get_by_id(self, id: int, /) -> EntityWrapper[T]:
        try:

            def filter_on_id(wrapper: EntityWrapper[T]):
                entity_id = getattr(wrapper.entity, "id", None)
                assert entity_id is not None, (
                    f"EntityType '{wrapper.locator.entityType}' does not provide an id"
                )
                return entity_id == id

            return self.get_where(filter_on_id)
        except Exception as err:
            raise utils.create_error(f"No entity found for id: '{id}'") from err

    def get_by_name(self, name: str, /) -> EntityWrapper[T]:
        try:
            return self.get_where(lambda w: w.entity.name == name)
        except Exception as err:
            raise utils.create_error(f"No entity found for name: '{name}'") from err

    def get_many_where(
        self, filter_: Callable[[EntityWrapper[T]], bool], /, locator: LocatorOrString | None = None
    ) -> list[EntityWrapper[T]]:
        iter = filter(filter_, self.__entities.values())
        wrappers: list[EntityWrapper[T]] = []

        with self.lock:
            for wrapper in iter:
                if locator is not None and wrapper.locator not in self.__ensure_locator(locator):
                    continue
                if not wrapper.resolved:
                    self.model.resolve_wrapper(wrapper)
                wrappers.append(wrapper)

        return wrappers

    def get_many(self, locator: LocatorOrString, /) -> list[EntityWrapper[T]]:
        locator_ = self.__ensure_locator(locator)
        return self.get_many_where(lambda w: w.locator in locator_)

    def get_all(self, /) -> list[EntityWrapper[T]]:
        return list(self.values())

    def add(self, locator: LocatorOrString, /, wrapper: EntityWrapper[T]) -> None:
        with self.lock:
            locator_ = self.__ensure_locator(locator)
            if locator_ in self:
                raise utils.create_error(Exception(f"Locator already exists in model: {locator_}"))

            self.__entities[locator_] = wrapper

    def remove(self, locator: LocatorOrString, /) -> None:
        with self.lock:
            locator_ = self.__ensure_locator(locator)
            if locator_ not in self:
                raise utils.create_error(errors.EntityNotFoundError(entity=str(locator)))

            del self.__entities[locator_]

    # methods to provide a "dictionary-like" experience

    def __getitem__(self, locator: LocatorOrString) -> EntityWrapper[T]:
        return self.get(locator)

    def __setitem__(self, locator: LocatorOrString, /, wrapper: EntityWrapper[T]) -> None:
        self.add(locator, wrapper)

    def __delitem__(self, locator: LocatorOrString, /) -> None:
        self.remove(locator)

    def __contains__(self, locator: LocatorOrString) -> bool:
        return self.__ensure_locator(locator) in self.__entities

    def __len__(self) -> int:
        return len(self.__entities)

    def __iter__(self) -> Generator[Locator, None, None]:
        yield from self.__entities

    def values(self) -> Generator[EntityWrapper[T], None, None]:
        yield from self.__entities.values()

    def items(self) -> Generator[tuple[Locator, EntityWrapper[T]], None, None]:
        yield from self.__entities.items()

    def iter(self) -> Generator[Locator, None, None]:
        return self.__iter__()


class PropertyReference(p.PropertyReference):
    """
    Sub-class of `datam8.property.PropertyReference` for actual use with the
    generator offering further functionality.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, p.PropertyReference):
            return self.property == other.property and self.value == other.value
        else:
            return False

    def __hash__(self):
        return hash((self.property, self.value))

    @staticmethod
    def from_model_ref(ref: p.PropertyReference, /) -> PropertyReference:
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
    objects parsed from the jso files should mostly not handled directly and
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

    def reset(self, locator: Locator, /, *, source_file: Path | None = None) -> None:
        self.locator = locator
        self._properties = {}
        self.resolved = False
        self._changed = False
        self._deleted = False
        self.source_file = source_file or self.source_file

    def has_property(self, property_name: str, /) -> bool:
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

    def update(self, **kwargs: Any) -> None:
        new_entity = self.entity.model_copy(update=kwargs, deep=True)

        try:
            new_entity = type(new_entity).model_validate(new_entity)
        except ValidationError as err:
            raise utils.create_error(err, status_code=520)

        self.entity = new_entity
        self._changed = True


class IModel(Protocol):
    def resolve_wrapper[T: b.BaseEntityType](
        self, wrapper: EntityWrapper[T], /
    ) -> EntityWrapper[T]: ...


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
