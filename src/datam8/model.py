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
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, SkipValidation, ValidationError

from datam8_model import attribute as a
from datam8_model import base as b
from datam8_model import data_product as dp
from datam8_model import data_source as ds
from datam8_model import data_type as dt
from datam8_model import folder as f
from datam8_model import model as m
from datam8_model import property as p
from datam8_model import solution as s
from datam8_model import zone as z

from . import config, logging, opts, utils
from . import model_exceptions as errors

logger = logging.getLogger(__name__)


type BaseEntityDict[T: b.BaseEntityType] = dict[b.EntityType, list[T]]
type EntityDict[T: b.BaseEntityType] = dict[Locator, EntityWrapper[T]]
type EntityWrapperVariant = (
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


def class_from_type(_type: b.EntityType) -> type[b.BaseEntityType]:
    match _type:
        case b.EntityType.PROPERTIES:
            _class = p.Property
        case b.EntityType.PROPERTY_VALUES:
            _class = p.PropertyValue
        case b.EntityType.ZONES:
            _class = z.Zone
        case b.EntityType.MODEL_ENTITIES:
            _class = m.ModelEntity
        case b.EntityType.FOLDERS:
            _class = f.Folder
        case b.EntityType.DATA_TYPES:
            _class = dt.DataTypeDefinition
        case b.EntityType.DATA_SOURCES:
            _class = ds.DataSource
        case b.EntityType.DATA_SOURCE_TYPES:
            _class = ds.DataSourceType
        case b.EntityType.DATA_PRODUCTS:
            _class = dp.DataProduct
        case b.EntityType.DATA_MODULES:
            _class = dp.DataModule
        case b.EntityType.ATTRIBUTE_TYPES:
            _class = a.AttributeType

    return _class


def wrap_base_entity[T: b.BaseEntityType](
    entity_type: b.EntityType, locator_path: Path, entity: T, source_file: Path
) -> "EntityWrapper[T]":
    """
    Wraps an entity parsed from a json file into an EntityWrapper object.

    Parameters
    ----------
    entity_type : `EntityType`
        The entity type parsed from the json file.
    path : `Path`
        Source file where the entity was read from.
    entity : `T`, generic
        The entity to wrap.

    Returns
    -------
    `EntityWrapper[T]`
        The entity embedded into an EntityWrapper base on the generic type.
    """

    locator = Locator(
        entityType=entity_type.value,
        folders=locator_path.as_posix().split("/")[1:-1],
        entityName=getattr(entity, "name"),  # noqa: B009
    )

    return EntityWrapper[T](
        locator=locator,
        entity=entity,
        source_file=source_file,
    )


def new_empty_entity_type_dict() -> dict[b.EntityType, "list[EntityWrapper[b.BaseEntityType]]"]:
    """Create an empty dictionary to every available BaseEntityType.

    WARNING: The type of the result list items is not set.

    Returns
    -------
    list[Any]
        A dictionary with a key for every available entity type, mapping to an
        empty list.
    """
    return {_type: [] for _type in b.EntityType}


def _ensure_locator(locator: "str | Locator") -> "Locator":
    if isinstance(locator, str):
        return Locator.from_path(locator)

    return locator


class Locator(m.Locator):
    """
    Sub-class of `datam8.model.Locator` offerting further functionality.
    Should be used instead of its base class.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.__str__() == other

        elif not isinstance(other, Locator):
            raise TypeError(f"Cannot compare object of type {type(object)} with Locator")

        return all(
            [
                self.entityType == other.entityType,
                self.folders == other.folders,
                self.entityName == other.entityName,
            ]
        )

    def __contains__(self, other: object) -> bool:
        # ensure later checks are only done on locator objects
        if isinstance(other, str):
            other = Locator.from_path(other)
        elif not isinstance(other, Locator):
            raise TypeError(f"Cannot compare object of type {type(object)} with Locator")

        if self == other:
            return True

        # basic format checks before comparison the actual folder paths
        if (
            self.entityName is not None
            or self == other
            or self.entityType != other.entityType
            or len(self.folders) > len(other.folders)
        ):
            return False

        left_path = Path("/".join(other.folders))
        right_path = Path("/".join(self.folders))

        return left_path.is_relative_to(right_path)

    def __hash__(self):
        return hash(self.__str__())

    def __str__(self) -> str:
        parts = [self.entityType, *self.folders, self.entityName or ""]
        return "/".join(parts)

    @staticmethod
    def from_path(path: str) -> "Locator":
        """
        Creates a Locator object based on the given path.
        Trailing `.json` suffixes will be removed.

        Examples
        -------
        * `/modelEntities/raw/sales/other/Customer.json` resolves to
          - type: modelEntities
          - folders: [raw,sales,other]
          - entityName: Customer
        * `/dataSources/AdventureWorks` resolves to
          - type: dataSources
          - folders: []
          - entityName: AdventureWorks

        Parameters
        ----------
        path : `str`
            Physical or logical Path of a file/entity within the solution.

        Returns
        -------
        `Locator`
            An identifier unique for every object in the solution.
        """
        if path == "/":
            return ROOT_LOCATOR

        parts = path.removesuffix(".json").removeprefix("/").split("/")

        if any(
            [
                len(parts) < 1,
                parts[0] not in [member.value for member in b.EntityType],
            ]
        ):
            raise errors.InvalidLocatorError(path)

        if len(parts) == 1:
            locator = Locator(entityType=parts[0], folders=[], entityName=None)
        else:
            locator = Locator(
                entityType=parts[0],
                folders=parts[1:-1],
                entityName=None if parts[-1] == "" else parts[-1],
            )

        return locator

    @property
    def parent(self) -> "Locator | None":
        "Get the parent folder of this entity."

        if len(self.folders) < 1:
            return None

        new_folders = self.folders[:-1]
        entity_name = self.folders[-1]

        ploc = Locator(
            entityType=b.EntityType.FOLDERS.value,
            folders=new_folders,
            entityName=entity_name,
        )

        return ploc

    @property
    def parents(self) -> Iterator["Locator"]:
        "Returns all parent folders for this locator."

        current = self

        while current.parent:
            yield current.parent
            current = current.parent


ROOT_LOCATOR = Locator(entityType="/", folders=[], entityName=None)


@dataclass(slots=True)
class DeletedEntityRef:
    locator: Locator
    source_file: Path
    entity_type: b.EntityType
    replacement_locator: Locator | None = None


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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntityWrapper):
            return False

        return self.locator == other.locator

    @property
    def has_changed(self) -> bool:
        return self._changed

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

    def resolve(self, model: "Model") -> Self:
        """
        Recursively lookup concrete property value objects and write them to
        `EntityWrapper.properties`

        Parameters
        ----------
        model : `model.Model`
            The DataM8 model to lookup up the property values. This normally is the same
            model as the one this EntityWrapper resides in, but could also be a sperate model.

        Returns
        -------
        `EntityWrapper[T]`
            The resolved entity itself.
        """
        if self.resolved:
            logger.warning(
                "Tried resolving an already resolved entity, this should not be done"
                f" - {self.locator}"
            )
            return self

        if not hasattr(self.entity, "properties"):
            self.resolved = True
            return self

        property_references: list[p.PropertyReference] = getattr(self.entity, "properties") or []

        property_references += [
            pr
            for pr in self.get_inherited_property_references(model)
            # NOTE: properties set on the entity itself takes precedene to
            # inherited properties
            if pr not in property_references
        ]

        if len(property_references) > 0:
            self._resolve_properties(model, property_references)

        self._resolve_model_attributes(model)
        self.resolved = True

        return self

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


class Model:
    """
    The main class that all data from the datam8 solution will be stored in.

    It will also be the main interface for use in templates. Nothing else should
    be available there directly.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )
    solution: Annotated[s.Solution, Field(frozen=True)]
    properties: Annotated[EntityDict[p.Property], SkipValidation]
    propertyValues: Annotated[EntityDict[p.PropertyValue], SkipValidation]
    zones: Annotated[EntityDict[z.Zone], SkipValidation]
    dataTypes: Annotated[EntityDict[dt.DataTypeDefinition], SkipValidation]
    dataSources: Annotated[EntityDict[ds.DataSource], SkipValidation]
    dataSourceTypes: Annotated[EntityDict[ds.DataSourceType], SkipValidation]
    dataProducts: Annotated[EntityDict[dp.DataProduct], SkipValidation]
    dataModules: Annotated[EntityDict[dp.DataModule], SkipValidation]
    attributeTypes: Annotated[EntityDict[a.AttributeType], SkipValidation]
    folders: Annotated[EntityDict[f.Folder], SkipValidation]
    modelEntities: Annotated[EntityDict[m.ModelEntity], SkipValidation]

    def __init__(self, solution: s.Solution, **kwargs: EntityDict):
        self.solution = solution

        for k, v in kwargs.items():
            setattr(self, k, v)

        self._model_files: dict[Path, EntityFileRef] = {}
        """Internal dictionary to allow easy mapping of files and their entities"""
        self._deleted_entities: dict[Locator, DeletedEntityRef] = {}
        """Track deleted locators until they are persisted to disk."""

        self.__next_model_id = max([w.entity.id for w in self.modelEntities.values()])

    def get_next_model_id(self) -> int:
        next = self.__next_model_id
        self.__next_model_id += 1
        return next

    def refresh_file_references(self) -> None:
        self._model_files = {}

        for _wrapper in self.get_entity_iterator():
            if _wrapper.source_file not in self._model_files:
                self._model_files[_wrapper.source_file] = EntityFileRef(
                    _type=b.EntityType(_wrapper.locator.entityType), file_path=_wrapper.source_file
                )

            self._model_files[_wrapper.source_file].locators.append(_wrapper.locator)

    def resolve(self) -> None:
        "Resolve all entities by iterating over them."
        for wrapper in self.get_entity_iterator():
            wrapper.resolve(self)

    def get_entity_iterator(self) -> Iterator[EntityWrapperVariant]:
        for entity_type in b.EntityType:
            entities: EntityDict = getattr(self, entity_type.value)
            for _, wrapper in entities.items():
                yield wrapper

    def get_generator_target(self, name: str) -> s.GeneratorTarget:
        if name == opts.default_target:
            return self.get_generator_default_target()

        for target in self.solution.generatorTargets:
            if target.name == name:
                return target

        raise utils.create_error(errors.InvalidGeneratorTargetError(name))

    def get_generator_default_target(self) -> s.GeneratorTarget:
        default_targets = list(filter(lambda t: t.isDefault, self.solution.generatorTargets))

        match len(default_targets):
            case 0:
                raise Exception("No default target defined")
            case 1:
                return default_targets.pop()
            case _:
                raise Exception("Multiple default targets defined")

    def _get_entity[T: b.BaseEntityType](
        self, entity_dict: EntityDict[T], entity_type: b.EntityType, name: str
    ) -> EntityWrapper[T]:
        locator = Locator.from_path(f"{entity_type.value}/{name}")

        if locator not in entity_dict:
            raise errors.EntityNotFoundError(f"{entity_type} {name}")

        entity = entity_dict[locator]

        if not entity.resolved:
            entity.resolve(self)

        return entity

    def get_zone(self, name: str) -> EntityWrapper[z.Zone]:
        """Get a zone by name."""
        wrapped_zone = self._get_entity(self.zones, b.EntityType.ZONES, name)
        return wrapped_zone

    def get_data_type(self, name: str) -> EntityWrapper[dt.DataTypeDefinition]:
        """Get a data type by name."""
        wrapped_data_type = self._get_entity(self.dataTypes, b.EntityType.DATA_TYPES, name)
        return wrapped_data_type

    def get_data_source(self, name: str) -> EntityWrapper[ds.DataSource]:
        """Get a data source by name."""
        wrapped_data_source = self._get_entity(self.dataSources, b.EntityType.DATA_SOURCES, name)
        return wrapped_data_source

    def get_data_source_type(self, name: str) -> EntityWrapper[ds.DataSourceType]:
        """Get a data source type by name."""
        wrapped_data_source_type = self._get_entity(
            self.dataSourceTypes, b.EntityType.DATA_SOURCE_TYPES, name
        )
        return wrapped_data_source_type

    def get_data_product(self, name: str) -> EntityWrapper[dp.DataProduct]:
        """Get a data product by name."""
        wrapped_data_product = self._get_entity(self.dataProducts, b.EntityType.DATA_PRODUCTS, name)
        return wrapped_data_product

    def get_data_module(self, data_product: str, name: str) -> dp.DataModule:
        """Get a data module for a data  product by name."""
        _data_product = self._get_entity(
            self.dataProducts, b.EntityType.DATA_PRODUCTS, data_product
        )

        # TODO: split data module up from data product and fill `self.dataModules`
        for data_module in _data_product.entity.dataModules:
            if data_module.name == name:
                return data_module

        raise errors.EntityNotFoundError(f"dataModule {data_product}:{name}")

    def get_attribute_type(self, name: str) -> EntityWrapper[a.AttributeType]:
        """Get an attribute type by name."""
        wrapped_attribute_type = self._get_entity(
            self.attributeTypes, b.EntityType.ATTRIBUTE_TYPES, name
        )
        return wrapped_attribute_type

    def get_property(self, name: str) -> EntityWrapper[p.Property]:
        """Get a property by name."""
        wrapped_property = self._get_entity(self.properties, b.EntityType.PROPERTIES, name)
        return wrapped_property

    def get_property_value(self, property: str, name: str) -> EntityWrapper[p.PropertyValue]:
        """Get a property value by its property and name."""
        property_values = [
            pv
            for pv in self.propertyValues.values()
            if pv.entity.property == property and pv.entity.name == name
        ]

        if len(property_values) != 1:
            raise errors.EntityNotFoundError(f"property value {property}/{name}")

        property_value = property_values.pop()

        if not property_value.resolved:
            return property_value.resolve(self)

        return property_value

    def get_folder(self, name: str) -> EntityWrapper[f.Folder]:
        """Get a folder by name."""
        wrapped_folder = self._get_entity(self.folders, b.EntityType.FOLDERS, name)
        return wrapped_folder

    def get_model_entity_by_id(self, id: int) -> EntityWrapper[m.ModelEntity]:
        """
        Retrieves a model entity by its id.

        Parameters
        ----------
        id : `int`
            The numeric id of the entity. Unrelated to the dynamic locator.

        Returns
        -------
        `EntityWrapper[ModelEntity]`

        Raises
        ------
        `EntityNotFoundError`
            When no model entity was found with this id.
        """
        for entity in self.modelEntities.values():
            if entity.entity.id == id:
                if not entity.resolved:
                    return entity.resolve(self)
                return entity

        raise errors.EntityNotFoundError(f"Model Id {id}")

    def get_entity_by_locator(self, locator: str | Locator) -> EntityWrapper[b.BaseEntityType]:
        """
        Retrieve a single entity by its locator.

        This is implemented as a directy dictionary key lookup, and will fail if
        the entity / locator does not exist.

        Parameters
        ----------
        locator : `str` or `Locator`
            The locator of the entity to retrieve.

        Returns
        -------
        `EntityWrapper`
            Of an unkown entity type. Needs to be type hinted manually if required.
        """
        locator = _ensure_locator(locator)
        wrapper: EntityWrapper[b.BaseEntityType] = getattr(self, locator.entityType)[locator]

        if not wrapper.resolved:
            wrapper.resolve(self)

        return wrapper

    def add_entity(
        self, locator: Locator, content: dict[str, Any]
    ) -> EntityWrapper[b.BaseEntityType]:
        _type = b.EntityType(locator.entityType)
        if _type in {b.EntityType.MODEL_ENTITIES, b.EntityType.FOLDERS}:
            source_file_path = self._resolve_source_file(locator)
        else:
            source_file_path = Path(config.solution_folder_path, *locator.folders)

        content.update({"id": self.get_next_model_id(), "name": locator.entityName})

        try:
            new_wrapper = EntityWrapper(
                locator=locator,
                source_file=source_file_path,
                entity=class_from_type(_type).from_dict(content),
                _changed=True,
            )
        except ValidationError as err:
            raise utils.create_error(err)

        entity_dict: EntityDict[b.BaseEntityType] = getattr(self, _type.value)

        if locator in entity_dict:
            raise utils.create_error(Exception(f"Locator already exists in model: {locator}"))

        new_wrapper._changed = True
        entity_dict[locator] = new_wrapper
        self.refresh_file_references()

        new_wrapper.resolve(self)

        return new_wrapper

    def get_entity_by_selector(
        self, selector: str, by: opts.Selectors
    ) -> EntityWrapper[b.BaseEntityType]:
        match by:
            case opts.Selectors.NAME:
                for wrapper in self.modelEntities.values():
                    if wrapper.entity.name == selector:
                        return wrapper  # pyright: ignore [reportReturnType]
                raise errors.EntityNotFoundError(selector)
            case opts.Selectors.ID:
                return self.get_model_entity_by_id(int(selector))  # pyright: ignore [reportReturnType]
            case opts.Selectors.LOCATOR:
                return self.get_entity_by_locator(selector)
            case _:
                raise NotImplementedError(f"by {by}")

    def get_all_entities(self) -> list[EntityWrapperVariant]:
        return [wrapper for wrapper in self.get_entity_iterator()]

    def get_entities(self, search_locator: str | Locator) -> list[EntityWrapperVariant]:
        """
        Retrieve a list of EntityWrappers that are hierarchically underneath the
        given locator.

        Parameters
        ----------
        search_locator : `str` or `Locator`
            The parent locator to search for entities.

        Returns
        -------
        `list[EntityWrapper]`
            Since the entityType is not known beforehand type hints for the
            entities are not available automatically and need to be added manually.
        """
        search_locator = _ensure_locator(search_locator)

        if search_locator == ROOT_LOCATOR:
            return self.get_all_entities()

        child_locators = self.get_child_locators(search_locator)

        if len(child_locators) == 0:
            return []

        entity_dict: dict[Locator, EntityWrapperVariant] = getattr(self, search_locator.entityType)
        entities = [
            entity_dict[_loc] if entity_dict[_loc].resolved else entity_dict[_loc].resolve(self)
            for _loc in child_locators
        ]

        return entities

    def get_child_locators(self, search_locator: str | Locator) -> list[Locator]:
        """
        Retrieve all enties located underneath the given locator, works for alle
        items not only model entities.

        Only locators to actual entities are return, no "intermediate" locators point to folders.

        Parameters
        ----------
        search_locator : `str` or `Locator`
            The locator used for searching. It itself is not included in the results.

        Returns
        -------
        `list[Locator]`
            Since the entityType is not known beforehand type hints for the
            entities are not available automatically and need to be added manually.
        """
        search_locator = _ensure_locator(search_locator)
        locators_to_be_compared: list[Locator] = [
            _loc for _loc in getattr(self, search_locator.entityType)
        ]
        found_locators = list(filter(lambda _loc: _loc in search_locator, locators_to_be_compared))

        return found_locators

    def _is_locator_in_scope(self, scope_locator: Locator, candidate: Locator) -> bool:
        if scope_locator == ROOT_LOCATOR:
            return True

        if scope_locator.entityName is None:
            return candidate.entityType == scope_locator.entityType and candidate in scope_locator

        if scope_locator.entityType == b.EntityType.FOLDERS.value:
            folder_path = (*scope_locator.folders, scope_locator.entityName)

            if candidate.entityType == b.EntityType.FOLDERS.value:
                candidate_path = (*candidate.folders, candidate.entityName)
                return tuple(candidate_path[: len(folder_path)]) == folder_path

            if candidate.entityType == b.EntityType.MODEL_ENTITIES.value:
                return tuple(candidate.folders[: len(folder_path)]) == folder_path

            return False

        return candidate.entityType == scope_locator.entityType and candidate == scope_locator

    def _collect_folder_subtree_locators(
        self, folder_locator: Locator
    ) -> tuple[list[Locator], list[Locator]]:
        folder_locators = [
            locator
            for locator in self.folders
            if self._is_locator_in_scope(folder_locator, locator)
        ]
        model_entity_locators = [
            locator
            for locator in self.modelEntities
            if self._is_locator_in_scope(folder_locator, locator)
        ]

        return folder_locators, model_entity_locators

    def _record_deleted_wrapper(self, wrapper: EntityWrapperVariant) -> None:
        self._deleted_entities[wrapper.locator] = DeletedEntityRef(
            locator=wrapper.locator,
            source_file=wrapper.source_file,
            entity_type=b.EntityType(wrapper.locator.entityType),
        )

    def _record_relocated_wrapper(
        self, wrapper: EntityWrapperVariant, replacement_locator: Locator
    ) -> None:
        self._deleted_entities[wrapper.locator] = DeletedEntityRef(
            locator=wrapper.locator,
            source_file=wrapper.source_file,
            entity_type=b.EntityType(wrapper.locator.entityType),
            replacement_locator=replacement_locator,
        )

    def _resolve_source_file(self, locator: Locator) -> Path:
        entity_type = b.EntityType(locator.entityType)
        if locator.entityName is None:
            raise ValueError(f"Locator does not reference an entity: {locator}")
        entity_name = locator.entityName

        if entity_type == b.EntityType.MODEL_ENTITIES:
            return (
                config.solution_folder_path
                / self.solution.modelPath
                / Path(*locator.folders, f"{entity_name}.json")
            )

        if entity_type == b.EntityType.FOLDERS:
            return (
                config.solution_folder_path
                / self.solution.modelPath
                / Path(*locator.folders, entity_name, ".properties.json")
            )

        raise ValueError(f"Unsupported entity type for source file resolution: {locator}")

    def _rewrite_locator(
        self, locator: Locator, from_locator: Locator, to_locator: Locator
    ) -> Locator:
        assert locator.entityName is not None
        assert from_locator.entityName is not None
        assert to_locator.entityName is not None

        if locator.entityType == b.EntityType.MODEL_ENTITIES.value:
            if from_locator.entityType == b.EntityType.MODEL_ENTITIES.value:
                return to_locator

            from_path = (*from_locator.folders, from_locator.entityName)
            suffix = locator.folders[len(from_path) :]
            return Locator(
                entityType=locator.entityType,
                folders=[*to_locator.folders, to_locator.entityName, *suffix],
                entityName=locator.entityName,
            )

        from_path = (*from_locator.folders, from_locator.entityName)
        to_path = (*to_locator.folders, to_locator.entityName)
        current_path = (*locator.folders, locator.entityName)
        suffix = current_path[len(from_path) :]
        new_path = (*to_path, *suffix)
        return Locator(
            entityType=locator.entityType,
            folders=list(new_path[:-1]),
            entityName=new_path[-1],
        )

    def _prepare_moved_wrapper(
        self, wrapper: EntityWrapperVariant, new_locator: Locator
    ) -> EntityWrapperVariant:
        wrapper.locator = new_locator
        wrapper.source_file = self._resolve_source_file(new_locator)
        wrapper.entity.name = new_locator.entityName  # type: ignore[attr-defined]
        wrapper.resolved = False
        wrapper._properties = {}
        wrapper._changed = True
        return wrapper

    def delete_entity(self, locator: str | Locator) -> list[Locator]:
        delete_locator = _ensure_locator(locator)

        if delete_locator.entityName is None:
            raise ValueError(f"Locator does not reference an entity: {delete_locator}")

        if delete_locator.entityType == b.EntityType.FOLDERS.value:
            if delete_locator not in self.folders:
                raise errors.EntityNotFoundError(str(delete_locator))

            folder_locators, model_entity_locators = self._collect_folder_subtree_locators(
                delete_locator
            )
            removed_locators: list[Locator] = []

            for folder_loc in sorted(folder_locators, key=lambda item: len(item.folders), reverse=True):
                wrapper = self.folders.pop(folder_loc)
                self._record_deleted_wrapper(wrapper)
                removed_locators.append(folder_loc)

            for model_locator in model_entity_locators:
                wrapper = self.modelEntities.pop(model_locator)
                self._record_deleted_wrapper(wrapper)
                removed_locators.append(model_locator)

            self.refresh_file_references()
            return removed_locators

        entity_dict: dict[Locator, EntityWrapperVariant] = getattr(self, delete_locator.entityType)
        if delete_locator not in entity_dict:
            raise errors.EntityNotFoundError(str(delete_locator))

        target_wrapper = entity_dict[delete_locator]
        removed_locators = [delete_locator]

        if delete_locator.entityType in {
            b.EntityType.MODEL_ENTITIES.value,
            b.EntityType.FOLDERS.value,
        }:
            wrapper = entity_dict.pop(delete_locator)
            self._record_deleted_wrapper(wrapper)
        else:
            file_wrappers = [
                wrapper
                for wrapper in entity_dict.values()
                if wrapper.source_file == target_wrapper.source_file
            ]
            removed_locators = [wrapper.locator for wrapper in file_wrappers]
            for wrapper in file_wrappers:
                entity_dict.pop(wrapper.locator)
                self._record_deleted_wrapper(wrapper)

        self.refresh_file_references()
        return removed_locators

    def move_entity(self, from_locator: str | Locator, to_locator: str | Locator) -> list[Locator]:
        source_locator = _ensure_locator(from_locator)
        target_locator = _ensure_locator(to_locator)

        if source_locator.entityName is None or target_locator.entityName is None:
            raise ValueError("Move requires source and target locators to reference entities.")

        if source_locator.entityType != target_locator.entityType:
            raise ValueError("Move requires source and target locators of the same entity type.")

        entity_type = b.EntityType(source_locator.entityType)
        if entity_type not in {b.EntityType.MODEL_ENTITIES, b.EntityType.FOLDERS}:
            raise ValueError("Move is only supported for modelEntities and folders.")

        entity_dict: dict[Locator, EntityWrapperVariant] = getattr(self, entity_type.value)
        if source_locator not in entity_dict:
            raise errors.EntityNotFoundError(str(source_locator))
        if target_locator in entity_dict:
            raise FileExistsError(str(target_locator))

        if entity_type == b.EntityType.MODEL_ENTITIES:
            wrapper = entity_dict.pop(source_locator)
            self._record_relocated_wrapper(wrapper, target_locator)
            self._prepare_moved_wrapper(wrapper, target_locator)
            entity_dict[target_locator] = wrapper
            self.refresh_file_references()
            wrapper.resolve(self)
            return [source_locator, target_locator]

        source_path = (*source_locator.folders, source_locator.entityName)
        target_path = (*target_locator.folders, target_locator.entityName)
        if tuple(target_path[: len(source_path)]) == source_path:
            raise ValueError("Cannot move a folder into itself or one of its descendants.")

        folder_locators, model_entity_locators = self._collect_folder_subtree_locators(source_locator)
        folder_wrappers = [(loc, self.folders.pop(loc)) for loc in folder_locators]
        model_wrappers = [(loc, self.modelEntities.pop(loc)) for loc in model_entity_locators]

        moved_locators: list[Locator] = []
        for current_locator, wrapper in folder_wrappers:
            new_locator = self._rewrite_locator(current_locator, source_locator, target_locator)
            self._record_relocated_wrapper(wrapper, new_locator)
            self._prepare_moved_wrapper(wrapper, new_locator)
            self.folders[new_locator] = wrapper
            moved_locators.extend([current_locator, new_locator])

        for current_locator, wrapper in model_wrappers:
            new_locator = self._rewrite_locator(current_locator, source_locator, target_locator)
            self._record_relocated_wrapper(wrapper, new_locator)
            self._prepare_moved_wrapper(wrapper, new_locator)
            self.modelEntities[new_locator] = wrapper
            moved_locators.extend([current_locator, new_locator])

        self.refresh_file_references()
        for wrapper in list(self.folders.values()) + list(self.modelEntities.values()):
            if wrapper.has_changed and not wrapper.resolved:
                wrapper.resolve(self)

        return moved_locators

    def _cleanup_empty_model_dirs(self, file_paths: Sequence[Path]) -> None:
        model_root = config.solution_folder_path / self.solution.modelPath

        for file_path in file_paths:
            current_dir = file_path.parent
            while current_dir.exists() and current_dir != model_root:
                try:
                    current_dir.relative_to(model_root)
                except ValueError:
                    break

                if any(current_dir.iterdir()):
                    break

                current_dir.rmdir()
                current_dir = current_dir.parent

    def save(self, locator: str | None = None) -> None:
        """
        Saves the current state of the model or a specific entity to the corresponding json file.
        """
        scope_locator = _ensure_locator(locator or "/")
        changed_wrappers = [
            wrapper
            for wrapper in self.get_entity_iterator()
            if wrapper.has_changed and self._is_locator_in_scope(scope_locator, wrapper.locator)
        ]
        deleted_records = [
            record
            for record in self._deleted_entities.values()
            if self._is_locator_in_scope(scope_locator, record.locator)
            or (
                record.replacement_locator is not None
                and self._is_locator_in_scope(scope_locator, record.replacement_locator)
            )
        ]
        deleted_files = {record.source_file for record in deleted_records}
        if deleted_files:
            deleted_records = [
                record
                for record in self._deleted_entities.values()
                if record.source_file in deleted_files
                or self._is_locator_in_scope(scope_locator, record.locator)
                or (
                    record.replacement_locator is not None
                    and self._is_locator_in_scope(scope_locator, record.replacement_locator)
                )
            ]
            deleted_files = {record.source_file for record in deleted_records}

        if len(changed_wrappers) == 0 and len(deleted_records) == 0:
            logger.info("Nothing has changed")
            return

        # group change entities by file to minimize disk operations
        file_to_wrappers: dict[Path, list[EntityWrapperVariant]] = {}
        for _p, file_ref in self._model_files.items():
            _changed = [w for w in changed_wrappers if w.locator in file_ref.locators]
            if len(_changed) > 0:
                file_to_wrappers[_p] = _changed

        logger.info(
            "Saving %s changed files and %s deleted files, with %s changed entities and %s deleted locators",
            len(file_to_wrappers),
            len(deleted_files),
            len(changed_wrappers),
            len(deleted_records),
        )

        for _file in file_to_wrappers:
            if _file in deleted_files:
                continue

            if _file.exists():
                self._model_files[_file].update(file_to_wrappers[_file])
            else:
                self._model_files[_file].create(file_to_wrappers[_file])

            # reset _changed attribute for saved entities
            for wrapper in file_to_wrappers[_file]:
                wrapper._changed = False

        deleted_model_files: list[Path] = []
        for deleted_file in deleted_files:
            if deleted_file.exists():
                deleted_file.unlink()
                deleted_model_files.append(deleted_file)

        if deleted_model_files:
            self._cleanup_empty_model_dirs(deleted_model_files)

        for record in deleted_records:
            self._deleted_entities.pop(record.locator, None)

    def get_unsaved_entities(self) -> list[Locator]:
        unsaved_entities = [
            wrapper.locator for wrapper in self.get_entity_iterator() if wrapper.has_changed
        ]
        unsaved_entities.extend(record.locator for record in self._deleted_entities.values())
        return unsaved_entities


class EntityFileRef:
    def __init__(
        self, _type: b.EntityType, file_path: Path, locators: list[Locator] | None = None
    ) -> None:
        self._type: b.EntityType = _type
        self.file_path: Path = file_path
        self.locators: list[Locator] = locators or []

    def __repr__(self) -> str:
        return f"EntityFileRef({self._type} file={self.file_path})"

    def create(self, wrappers: list[EntityWrapperVariant]) -> None:
        entities = [wrapper.entity for wrapper in wrappers]
        _model = None

        match self._type:
            case b.EntityType.MODEL_ENTITIES:
                # model entities are special, since those files only contain a single entry
                assert len(entities) == 1, (
                    "Only one wrapper to update allowed when updateing single model file"
                )
                _model = entities[0]
            case b.EntityType.FOLDERS:
                _class = b.Folders
            case b.EntityType.PROPERTIES:
                _class = b.Properties
            case b.EntityType.PROPERTY_VALUES:
                _class = b.PropertyValues
            case b.EntityType.ZONES:
                _class = b.Zones
            case b.EntityType.DATA_TYPES:
                _class = b.DataTypes
            case b.EntityType.DATA_SOURCE_TYPES:
                _class = b.DataSourceTypes
            case b.EntityType.DATA_PRODUCTS:
                _class = b.DataProducts
            case b.EntityType.DATA_MODULES:
                _class = b.DataModules
            case b.EntityType.ATTRIBUTE_TYPES:
                _class = b.AttributeTypes
            case b.EntityType.DATA_SOURCES:
                _class = b.DataSources
            case _:
                raise utils.create_error(NotImplementedError(self._type.value))

        # one of both is always defined
        _model = _model or _class.from_dict(  # pyright: ignore [reportPossiblyUnboundVariable]
            {"type": self._type.value, self._type.value: entities},
        )

        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "x") as _file:
            _file.write(
                _model.model_dump_json(
                    indent=4,
                    exclude_defaults=True,
                    exclude_none=True,
                )
            )

    def update(self, wrappers: list[EntityWrapperVariant]) -> None:
        """
        Raises
        ------
        FileNotFoundError
            If the file to be updated does not exist
        """
        match self._type:
            case b.EntityType.MODEL_ENTITIES:
                current_content = m.ModelEntity.from_json_file(self.file_path)
                assert len(wrappers) == 1, (
                    "Only one wrapper to update allowed when updateing single model file"
                )
                current_content = wrappers[0].entity

            case _:
                current_content = b.BaseEntities.from_json_file(self.file_path)
                entities: list[Any] = list(getattr(current_content.root, self._type.value))

                for idx in range(len(wrappers)):
                    for existing_entity in entities:
                        if existing_entity.name == wrappers[idx].entity.name:
                            entities[idx] = wrappers[idx].entity

                setattr(current_content.root, self._type.value, entities)

        with open(self.file_path, "w") as _file:
            _file.write(
                current_content.model_dump_json(
                    indent=4,
                    exclude_defaults=True,
                    exclude_none=True,
                )
            )

        logger.info("Saved %s entities to %s", len(wrappers), self.file_path)
