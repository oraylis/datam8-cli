from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field

from dm8gen import utils
from dm8model import base as b
from dm8model import attribute as a
from dm8model import data_product as dp
from dm8model import data_source as ds
from dm8model import data_type as dt
from dm8model import folder as f
from dm8model import model as m
from dm8model import property as p
from dm8model import solution as s
from dm8model import zone as z

logger = utils.start_logger(__name__)


type EntityDict[T] = dict[str, EntityWrapper[T]]
type BaseEntityDict[T] = dict[b.EntityType, list[T]]
type ModelEntityDict = dict[str, m.ModelEntity]


def base_entity_dict_to_wrapper_dict[T](
    entities: BaseEntityDict[T], entity_type: b.EntityType
) -> EntityDict[T]:
    entity_dict: EntityDict[T] = {}

    for entity in entities[entity_type]:
        _key: str = getattr(entity, "name")
        _locator = Locator(
            entityType=entity_type.value, folders=[], entityName=_key
        )
        entity_dict[_key] = EntityWrapper[T](
            model_object=cast(T, entity), locator=_locator
        )

    return entity_dict


class Locator(m.Locator):
    def __str__(self) -> str:
        return "{}/{}/{}".format(
            self.entityType,
            "/".join(self.folders),
            self.entityName,
        )


class PropertyReference(p.PropertyReference):
    def __hash__(self):
        return hash(f"{self.property}|{self.value}")


class EntityWrapper[T](BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(), populate_by_name=True, extra="forbid"
    )
    locator: Locator
    model_object: T
    properties: dict[PropertyReference, p.PropertyValue] = {}

    def resolve_properties(self) -> None:
        pass

    def get_property_value(self, property: str, value: str) -> p.PropertyValue:
        ref = PropertyReference(property=property, value=value)

        if ref not in self.properties:
            raise EntityNotFoundException(f"property value `{ref}`")

        return self.properties[ref]


class Model(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        populate_by_name=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )
    solution: Annotated[s.Solution, Field(frozen=True)]
    properties: EntityDict[p.Property]
    propertyValues: EntityDict[p.PropertyValue]
    zones: EntityDict[z.Zone]
    dataTypes: EntityDict[dt.DataType]
    dataSources: EntityDict[ds.DataSource]
    dataProducts: EntityDict[dp.DataProduct]
    dataModules: EntityDict[dp.DataModule]
    attributeTypes: EntityDict[a.AttributeType]
    folders: EntityDict[f.Folder]
    modelEntities: EntityDict[m.ModelEntity]

    def get_model_entity_by_id(self, id: int) -> EntityWrapper[m.ModelEntity]:
        for entity in self.modelEntities.values():
            if entity.model_object.id == id:
                return entity

        raise EntityNotFoundException(f"Model Id {id}")

    def get_data_source(self, name: str) -> EntityWrapper[ds.DataSource]:
        sources = list(
            filter(
                lambda src: src.model_object.name == name,
                self.dataSources.values(),
            )
        )
        if len(sources) == 1:
            return sources.pop()

        raise EntityNotFoundException(f"DataSource {name}")

    def get_data_type(self, name: str) -> EntityWrapper[dt.DataType]:
        if name not in self.dataTypes:
            raise EntityNotFoundException(f"DataType {name}")

        return self.dataTypes[name]

    def get_data_product(self, name: str) -> EntityWrapper[dp.DataProduct]:
        if name not in self.dataProducts:
            raise EntityNotFoundException(f"DataProduct {name}")

        return self.dataProducts[name]

    # TODO: revisit for proper type hinting
    def get_base_entity(self, _type: b.EntityType, name: str) -> EntityWrapper:
        if name not in getattr(self, _type.value):
            raise EntityNotFoundException(f"{_type.value} {name}")

        return getattr(self, _type.value)[name]


class EntityNotFoundException(Exception):
    def __init__(
        self,
        entity: str,
        msg: str = "Entity was not found in model: %s",
        inner_exceptions: list[Exception] | None = None,
    ):
        Exception.__init__(self, msg % entity)

        self.inner_exceptions = inner_exceptions
        self.message = msg % entity
