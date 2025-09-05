from pathlib import Path
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field

from dm8gen import utils
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

logger = utils.start_logger(__name__)


type BaseEntityDict[T] = dict[b.EntityType, list[T]]
type EntityDict[T] = dict[Locator, EntityWrapper[T]]
type ModelEntityDict = dict[str, m.ModelEntity]


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
        folders=path.as_posix().split("/")[0:-1],
        entityName=getattr(entity, "name"),
    )

    return EntityWrapper[T](
        locator=locator,
        entity=cast(T, entity),
    )


def new_empty_base_entity_dict() -> BaseEntityDict:
    """Create an empty dictionary to every available BaseEntityType.

    WARNING: The generic type is not set and therefor unknown.
    """
    return {_type: [] for _type in b.EntityType}


class Locator(m.Locator):
    """
    Sub-class of `dm8gen.model.Locator` offerting further functionality.
    Should be used instead of its base class.
    """

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Locator):
            return False

        elif isinstance(other, str):
            return self.__str__() == other

        return all(
            [
                self.entityType == other.entityType,
                self.folders == other.folders,
                self.entityName == other.entityName,
            ]
        )

    def __hash__(self):
        return hash(self.__str__())

    def __str__(self) -> str:
        folders = "/".join(self.folders)

        if folders:
            return f"{self.entityType}/{folders}/{self.entityName}"
        else:
            return f"{self.entityType}/{self.entityName}"

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
        parts = path.removesuffix(".json").split("/")

        if "" in parts:
            parts.remove("")

        locator = Locator(
            entityType=parts[0],
            folders=parts[1:-1],
            entityName=parts[-1],
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
        protected_namespaces=(),
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
    properties: dict[PropertyReference, "EntityWrapper[p.PropertyValue]"] = {}
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
        """
        for pr in self.properties:
            if pr.property == property_name:
                return True

        return False


class Model(BaseModel):
    """
    The main class that all data from the datam8 solution will be stored in.

    It will also be the main interface for use in templates. Nothing else should
    be available there directly.
    """

    model_config = ConfigDict(
        protected_namespaces=(),
        populate_by_name=True,
        # extra="forbig",
        arbitrary_types_allowed=True,
    )
    solution: Annotated[s.Solution, Field(frozen=True)]
    properties: EntityDict[p.Property]
    propertyValues: EntityDict[p.PropertyValue]
    zones: EntityDict[z.Zone]
    dataTypes: EntityDict[dt.DataTypeDefinition]
    dataSources: EntityDict[ds.DataSource]
    dataProducts: EntityDict[dp.DataProduct]
    dataModules: EntityDict[dp.DataModule]
    attributeTypes: EntityDict[a.AttributeType]
    folders: EntityDict[f.Folder]
    modelEntities: EntityDict[m.ModelEntity]

    def _get_entity[T](
        self, entity_dict: EntityDict[T], entity_type: b.EntityType, name: str
    ) -> EntityWrapper[T]:
        locator = Locator.from_path(f"{entity_type.value}/{name}")

        if locator not in entity_dict:
            raise EntityNotFoundException(f"{entity_type} {name}")

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

        raise EntityNotFoundException(f"dataModule {data_product}:{name}")

    def get_attribute_type(self, name: str) -> EntityWrapper[a.AttributeType]:
        """Get an attribute type by name."""
        wrapped_attribute_type = self._get_entity(
            self.attributeTypes, b.EntityType.ATTRIBUTE_TYPES, name
        )
        return wrapped_attribute_type

    def get_folder(self, name: str) -> EntityWrapper[f.Folder]:
        """Get a folder by name."""
        wrapped_folder = self._get_entity(
            self.folders, b.EntityType.FOLDERS, name
        )
        return wrapped_folder

    def get_model_entity_by_id(self, id: int) -> EntityWrapper[m.ModelEntity]:
        for entity in self.modelEntities.values():
            if entity.entity.id == id:
                return entity

        raise EntityNotFoundException(f"Model Id {id}")


class EntityNotFoundException(Exception):
    def __init__(
        self,
        entity: str,
        msg: str = "Entity was not found in model: {}",
        inner_exceptions: list[Exception] | None = None,
    ):
        Exception.__init__(self, msg.format(entity))

        self.inner_exceptions = inner_exceptions
        self.message = msg.format(entity)
