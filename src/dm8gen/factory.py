from typing import cast

from pydantic import BaseModel

from dm8model.base import BaseEntityType
from dm8model import model
from dm8model.property import PropertyValue
from dm8model.solution import Solution


class Locator(model.Locator):
    def __str__(self) -> str:
        return "%s/%s/%s" % (
            self.zone,
            "/".join(self.folders),
            self.modelEntity,
        )


class EntityWrapper(BaseModel):
    entity: BaseEntityType
    properties: list[PropertyValue] = []
    locator: Locator | None = None


class Model(BaseModel):
    solution: Solution
    properties: dict[str, EntityWrapper]
    property_values: dict[str, EntityWrapper]
    zones: dict[str, EntityWrapper]
    data_types: dict[str, EntityWrapper]
    data_sources: dict[str, EntityWrapper]
    data_product: dict[str, EntityWrapper]
    data_modules: dict[str, EntityWrapper]
    attribute_types: dict[str, EntityWrapper]
    folders: dict[str, EntityWrapper]
    entities: dict[str, EntityWrapper]

    def get_model_entity_by_id(self, id: int):
        for entity in self.entities.values():
            if cast(model.ModelEntity, entity.entity).id == id:
                return entity

        raise EntityNotFoundException(id)


class EntityNotFoundException(Exception):
    def __init__(
        self,
        entity: str | int,
        msg: str = "Entity was not found in model: %s",
        inner_exceptions: list[Exception] = [],
    ):
        Exception.__init__(self, msg % entity)

        self.inner_exceptions = inner_exceptions
        self.message = msg % entity
