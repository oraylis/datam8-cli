# ruff: noqa: F401
from pathlib import Path

from datam8_model import base as b

from .entity_wrapper import EntityWrapper, EntityWrapperVariant, PropertyReference
from .locator import ROOT_LOCATOR, Locator
from .model import MODEL_DUMP_OPTIONS, EntityDict, Model


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

    new_wrapper = EntityWrapper[T](
        locator=locator,
        entity=entity,
        source_file=source_file,
    )

    return new_wrapper


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
