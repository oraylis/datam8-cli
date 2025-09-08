from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, SkipValidation

from dm8model import attribute as a
from dm8model import base as b
from dm8model import data_product as dp
from dm8model import data_source as ds
from dm8model import data_type as dt
from dm8model import folder as f
from dm8model import model as m
from dm8model import property as p
from dm8model import solution as s
from dm8model import zone as z

from . import model_exceptions as errors
from . import utils

logger = utils.start_logger(__name__)


type BaseEntityDict[T] = dict[b.EntityType, list[T]]
type EntityDict[T] = dict[Locator, EntityWrapper[T]]


def wrap_base_entity[T](
    entity_type: b.EntityType, path: Path, entity: T
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
        folders=path.as_posix().split("/")[1:-1],
        entityName=getattr(entity, "name"),
    )

    return EntityWrapper[T](
        locator=locator,
        entity=entity,
    )


def new_empty_entity_type_dict() -> dict[b.EntityType, list[Any]]:
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
    Sub-class of `dm8gen.model.Locator` offerting further functionality.
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
        parts = path.removesuffix(".json").removeprefix("/").split("/")
        # parts = [part for part in parts if part != ""]

        if any(
            [
                len(parts) < 2,
                parts[0] not in [member.value for member in b.EntityType],
            ]
        ):
            raise errors.InvalidLocatorError(path)

        locator = Locator(
            entityType=parts[0],
            folders=parts[1:-1],
            entityName=None if parts[-1] == "" else parts[-1],
        )

        return locator


class PropertyReference(p.PropertyReference):
    """
    Sub-class of `dm8gen.property.PropertyReference` for actual use with the
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
        ref : `dm8model.property.PropertyReference`
            Reference to a property value, directly parsed from the json files.
        """
        return PropertyReference(
            property=ref.property,
            value=ref.value,
        )


class EntityWrapper[T](BaseModel):
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

    model_config = ConfigDict(
        populate_by_name=True,
    )
    locator: Locator
    """
    A unique identifier for every entity/object within the solution.
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
    properties: dict[PropertyReference, Self] = {}
    """
    Additional properties than are dynamically defined within the solution.
    Contains actual properties based on the property references with the
    `entity.properties` attribute.
    """

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntityWrapper):
            return False

        return self.locator == other.locator

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

        Raises
        ------
        PropertiesNotResolvedError
            If the property references within the entity have not been resolved yet.
        """
        if not self.resolved:
            raise errors.PropertiesNotResolvedError(self.locator)

        for pr in self.properties:
            if pr.property == property_name:
                return True

        return False


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

    def get_generator_target(self, name: str) -> s.GeneratorTarget:
        for target in self.solution.generatorTargets:
            if target.name == name:
                return target

        raise errors.InvalidGeneratorTargetError(name)

    def _get_entity[T](
        self, entity_dict: EntityDict[T], entity_type: b.EntityType, name: str
    ) -> EntityWrapper[T]:
        locator = Locator.from_path(f"{entity_type.value}/{name}")

        if locator not in entity_dict:
            raise errors.EntityNotFoundError(f"{entity_type} {name}")

        return entity_dict[locator]

    def get_zone(self, name: str) -> EntityWrapper[z.Zone]:
        """Get a zone by name."""
        wrapped_zone = self._get_entity(self.zones, b.EntityType.ZONES, name)
        return wrapped_zone

    def get_data_type(self, name: str) -> EntityWrapper[dt.DataTypeDefinition]:
        """Get a data type by name."""
        wrapped_data_type = self._get_entity(
            self.dataTypes, b.EntityType.DATA_TYPES, name
        )
        return wrapped_data_type

    def get_data_source(self, name: str) -> EntityWrapper[ds.DataSource]:
        """Get a data source by name."""
        wrapped_data_source = self._get_entity(
            self.dataSources, b.EntityType.DATA_SOURCES, name
        )
        return wrapped_data_source

    def get_data_source_type(self, name: str) -> EntityWrapper[ds.DataSourceType]:
        """Get a data source type by name."""
        wrapped_data_source_type = self._get_entity(
            self.dataSourceTypes, b.EntityType.DATA_SOURCE_TYPES, name
        )
        return wrapped_data_source_type

    def get_data_product(self, name: str) -> EntityWrapper[dp.DataProduct]:
        """Get a data product by name."""
        wrapped_data_product = self._get_entity(
            self.dataProducts, b.EntityType.DATA_PRODUCTS, name
        )
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
        wrapped_property = self._get_entity(
            self.properties, b.EntityType.PROPERTIES, name
        )
        return wrapped_property

    def get_property_value(
        self, property: str, name: str
    ) -> EntityWrapper[p.PropertyValue]:
        """Get a property value by its property and name."""
        property_values = [
            pv
            for pv in self.propertyValues.values()
            if pv.entity.property == property and pv.entity.name == name
        ]

        if len(property_values) != 1:
            raise errors.EntityNotFoundError(f"property value {property}/{name}")

        return property_values.pop()

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
                return entity

        raise errors.EntityNotFoundError(f"Model Id {id}")

    def get_entity_by_locator(self, locator: str | Locator) -> EntityWrapper:
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

        return getattr(self, locator.entityType)[locator]

    def get_entities(self, search_locator: str | Locator) -> list[EntityWrapper]:
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
        child_locators = self.get_child_locators(search_locator)

        if not child_locators:
            raise Exception("No entites found")

        entities: EntityDict = getattr(self, search_locator.entityType)

        return [entities[_loc] for _loc in child_locators]

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
        found_locators = list(
            filter(lambda _loc: _loc in search_locator, locators_to_be_compared)
        )

        return found_locators
