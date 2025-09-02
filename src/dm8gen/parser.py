"""
This module handles all parsing of json files into generator internal objects.
"""

import pathlib
from typing import TypeAlias, cast

from pydantic import ValidationError

from dm8gen.factory import EntityWrapper, Model, Locator
from dm8gen import config
from dm8model import base as b, model as m, solution as s
from dm8model.attribute import AttributeType
from dm8model.data_product import DataModule, DataProduct
from dm8model.data_source import DataSource
from dm8model.data_type import DataTypeDefinition
from dm8model.folder import Folder
from dm8model.property import Property, PropertyValue
from dm8model.zone import Zone

from . import utils

logger = utils.start_logger(__name__)

BaseEntityDict: TypeAlias = dict[b.EntityType, list[b.BaseEntityType]]


def __parse_base_entity_type(entity_type: str) -> b.EntityType:
    return {e.value: e for e in b.EntityType}[entity_type]


def __parse_base_entity_file(
    path: pathlib.Path,
) -> tuple[b.EntityType, list[b.BaseEntityType]]:
    base_entities = b.BaseEntities.from_json_file(path)
    rel_path = path.relative_to(config.solution_folder_path)

    entities_type = __parse_base_entity_type(base_entities.root.type)
    entities = getattr(base_entities.root, entities_type.value)

    logger.debug("%s: Success", rel_path)

    return entities_type, entities


def __parse_solution_file(path: pathlib.Path) -> s.Solution:
    solution = s.Solution.from_json_file(path)

    logger.info("Successfully parsed solution file with schema version: %s", solution.schemaVersion)
    logger.debug(solution.model_dump_json(indent=4))
    return solution


def __parse_base_entities(solution: s.Solution) -> BaseEntityDict:
    base_entities: BaseEntityDict = {_type: [] for _type in b.EntityType}
    file_count = 0

    for base_file in [
        *(config.solution_folder_path / solution.basePath).glob("**/*.json"),
        *(config.solution_folder_path / solution.modelPath).glob(
            "**/.properties.json"
        ),
    ]:
        _type, parsed_entities = __parse_base_entity_file(base_file)
        base_entities[_type] = parsed_entities

        file_count += 1

    logger.info("Successfully parsed base entities: %d", file_count)

    return base_entities


def __parse_model_entity_file(
    path: pathlib.Path,
) -> m.ModelEntity | Exception:
    rel_path = path.relative_to(config.solution_folder_path)

    try:
        model_entity = m.ModelEntity.from_json_file(path)
    except ValidationError as err:
        return err

    logger.debug("%s: Success", rel_path)
    return model_entity


def __parse_model_entities(
    model_path: pathlib.Path,
) -> dict[str, EntityWrapper]:
    model_entities: dict[str, EntityWrapper] = {}
    parse_errors: dict[pathlib.Path, Exception] = {}
    file_count = 0

    # model_files = [file for file in model_path.glob("**/*.json") if not file.match(".properties.json")]

    for model_file in model_path.glob("**/*.json"):
        if model_file.match(".properties.json"):
            continue

        model_entity_or_err = __parse_model_entity_file(model_file)
        rel_path = model_file.relative_to(model_path)

        if isinstance(model_entity_or_err, ValidationError):
            parse_errors[rel_path] = model_entity_or_err
            continue

        # NOTE: explicitly cast to ModelEntity for type hinting only
        model_entities[rel_path.as_posix()] = EntityWrapper(
            locator=__compose_locator(rel_path.as_posix()),
            entity=cast(m.ModelEntity, model_entity_or_err),
        )

        file_count += 1

    if parse_errors:
        for file, error in parse_errors.items():
            logger.error("%s: \n%s", file, error)

        raise ModelParseException(
            inner_exceptions=[err for err in parse_errors.values()]
        )

    logger.info("Successfully parsed model entities: %d", file_count)

    return model_entities


@utils.get_logger
def parse_full_solution(
    solution_path: pathlib.Path, lazy: bool = False
) -> Model:
    """Load and parses all json files in a solution into generator internal objects.

    Args
        solution_path (Path): path to the solution file (.dm8s)
        lazy (bool): if lazy loading is enabled model entities will not be loaded,
            which needs to be handeled afterwards on the fly.

    Returns
        The parsed model from files BUT not validated in regards to internal
        references.
    """
    solution = __parse_solution_file(solution_path)

    base_path = solution_path.parent.absolute() / solution.basePath
    model_path = solution_path.parent.absolute() / solution.modelPath

    logger.debug("BasePath: %s", base_path.relative_to(solution_path.parent))
    logger.debug("ModelPath: %s", model_path.relative_to(solution_path.parent))

    base_entities = __parse_base_entities(solution)
    model_entites = {}

    if not lazy:
        model_entites = __parse_model_entities(model_path)

    model = Model(
        solution=solution,
        properties={
            cast(Property, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.PROPERTIES]
        },
        property_values={
            cast(PropertyValue, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.PROPERTY_VALUES]
        },
        zones={
            cast(Zone, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.ZONES]
        },
        data_types={
            cast(DataTypeDefinition, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.DATA_TYPES]
        },
        attribute_types={
            cast(AttributeType, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.ATTRIBUTE_TYPES]
        },
        data_modules={
            cast(DataModule, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.DATA_MODULES]
        },
        data_product={
            cast(DataProduct, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.DATA_PRODUCTS]
        },
        data_sources={
            cast(DataSource, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.DATA_SOURCES]
        },
        folders={
            cast(Folder, p).name: EntityWrapper(entity=p)
            for p in base_entities[b.EntityType.FOLDERS]
        },
        entities=model_entites,
    )

    # logger.debug("Parse model:\n%s", model.model_dump_json())
    logger.info("Successfully parsed all files in solution")

    return model


def __compose_locator(path: str) -> Locator:
    parts = path.removesuffix(".json").split("/")
    locator = Locator(
        zone=parts[0],
        folders=parts[1:-2],
        modelEntity=parts[-1],
    )
    return locator


class ModelParseException(Exception):
    def __init__(
        self,
        msg="Error(s) occured during model files parsing.",
        inner_exceptions: list[Exception] = [],
    ):
        Exception.__init__(self, msg)

        self.inner_exceptions = inner_exceptions
        self.message = msg
