"""
This module handles all parsing of json files into generator internal objects.
"""

import pathlib
from concurrent import futures

from pydantic import ValidationError

from dm8gen import config
from dm8gen.model import (
    EntityWrapper,
    Model,
    EntityDict,
    BaseEntityDict,
    Locator,
)
from dm8model import base as b
from dm8model import model as m
from dm8model import solution as s

from . import utils

logger = utils.start_logger(__name__)


def __parse_base_entity_type(entity_type: str) -> b.EntityType:
    return {e.value: e for e in b.EntityType}[entity_type]


def __parse_solution_file(path: pathlib.Path) -> s.Solution:
    solution = s.Solution.from_json_file(path)

    logger.info(
        "Parsed solution file with schema version: %s",
        solution.schemaVersion,
    )
    logger.debug(solution.model_dump_json(indent=4))
    return solution


def __parse_base_entity_file(
    path: pathlib.Path,
) -> tuple[b.EntityType, list[b.BaseEntityType]]:
    base_entities = b.BaseEntities.from_json_file(path)
    rel_path = path.relative_to(config.solution_folder_path)

    entities_type = __parse_base_entity_type(base_entities.root.type)
    entities = getattr(base_entities.root, entities_type.value)

    logger.debug(rel_path)

    return entities_type, entities


def __parse_base_entities(
    base_path: pathlib.Path,
    model_path: pathlib.Path,
    executor: futures.ThreadPoolExecutor,
) -> BaseEntityDict[b.BaseEntityType]:
    logger.debug(f"Scanning {base_path} for base entities")
    logger.debug(f"Scanning {model_path} for folder entities")

    base_files = [
        *(config.solution_folder_path / base_path).glob("**/*.json"),
        *(config.solution_folder_path / model_path).glob("**/.properties.json"),
    ]

    base_entities: BaseEntityDict[b.BaseEntityType] = {
        # combine with all entries from enum to ensure existance of keys
        **{_type: [] for _type in b.EntityType},
        **{
            _type: parsed_entities
            for _type, parsed_entities in executor.map(
                __parse_base_entity_file, base_files
            )
        },
    }

    logger.info("Parsed base entities: %d", len(base_entities))

    return base_entities


def __parse_model_entity_file(
    path: pathlib.Path,
) -> tuple[pathlib.Path, m.ModelEntity | ValidationError]:
    rel_path = path.relative_to(config.solution_folder_path)

    try:
        model_entity = m.ModelEntity.from_json_file(path)
    except ValidationError as err:
        logger.error("%s: \n%s", path, err)
        return rel_path, err

    logger.debug(rel_path)

    return rel_path, model_entity


def __parse_model_entities(
    path: pathlib.Path,
    executor: futures.ThreadPoolExecutor,
) -> EntityDict[m.ModelEntity]:
    model_entities: EntityDict[m.ModelEntity] = {}
    parse_errors: dict[pathlib.Path, ValidationError] = {}

    logger.debug(f"Scanning {path} for model entities")

    model_files = [
        file
        for file in (config.solution_folder_path / path).glob("**/*.json")
        if not file.match(".properties.json")
    ]

    if not model_files:
        logger.warning("Not model entity files found")

    loaded_entities = executor.map(__parse_model_entity_file, model_files)

    for rel_path, model_entity_orr_err in loaded_entities:
        if isinstance(model_entity_orr_err, m.ModelEntity):
            model_entities[rel_path.as_posix()] = EntityWrapper[m.ModelEntity](
                locator=__compose_locator(
                    "modelEntities/"
                    + rel_path.as_posix().removeprefix(path.as_posix())
                ),
                # NOTE: explicitly cast to ModelEntity for type hinting only
                model_object=model_entity_orr_err,
            )
        else:
            parse_errors[rel_path] = model_entity_orr_err

    if parse_errors:
        raise ModelParseException(
            inner_exceptions=[err for err in parse_errors.values()]
        )

    logger.info("Parsed model entities: %d", len(model_files))

    return model_entities


@utils.print_progress_async
@utils.get_logger
async def parse_full_solution(solution_path: pathlib.Path) -> Model:
    """Load and parses all json files in a solution into generator internal objects.

    Executes loading & parsing of json files via multi threading.

    Args
        solution_path (Path): path to the solution file (.dm8s)
        lazy (bool): if lazy loading is enabled model entities will not be loaded,
            which needs to be handeled afterwards on the fly.

    Returns
        The parsed model from files BUT not validated in regards to internal
        references.
    """
    logger.debug("Start parsing solution")

    solution = __parse_solution_file(solution_path)

    executor = futures.ThreadPoolExecutor()

    worker_model = executor.submit(
        __parse_model_entities, solution.modelPath, executor
    )
    worker_base = executor.submit(
        __parse_base_entities, solution.basePath, solution.modelPath, executor
    )

    base_entities = worker_base.result()
    model_entities = worker_model.result()

    model = Model(
        solution=solution,
        properties={},  # base_dict_to_entity_dict(base_entities, b.EntityType.PROPERTIES),
        # properties=base_entity_dict_to_wrapper_dict[p.Property](base_entities, b.EntityType.PROPERTIES),
        propertyValues={},  # base_dict_to_entity_dict(base_entities, b.EntityType.PROPERTY_VALUES),
        # propertyValues=base_entity_dict_to_wrapper_dict[p.PropertyValue](base_entities, b.EntityType.PROPERTY_VALUES),
        zones={},  # base_dict_to_entity_dict(base_entities, b.EntityType.ZONES),
        # zones=base_entity_dict_to_wrapper_dict[z.Zone](base_entities, b.EntityType.ZONES),
        dataTypes=base_dict_to_entity_dict(
            base_entities, b.EntityType.DATA_TYPES
        ),  # base_dict_to_entity_dict(base_entities, b.EntityType.DATA_TYPES),
        # dataTypes=base_entity_dict_to_wrapper_dict[dt.DataTypeDefinition](base_entities, b.EntityType.DATA_TYPES),
        attributeTypes={},  # base_dict_to_entity_dict(base_entities, b.EntityType.ATTRIBUTE_TYPES),
        # attributeTypes=base_entity_dict_to_wrapper_dict[a.AttributeType](base_entities, b.EntityType.ATTRIBUTE_TYPES),
        dataModules=base_dict_to_entity_dict(base_entities, b.EntityType.DATA_MODULES),
        # dataModules=base_entity_dict_to_wrapper_dict[dp.DataModule](base_entities, b.EntityType.DATA_MODULES),
        dataProducts=base_dict_to_entity_dict(base_entities, b.EntityType.DATA_PRODUCTS),
        # dataProduct=base_entity_dict_to_wrapper_dict[dp.DataProduct](base_entities, b.EntityType.DATA_PRODUCTS),
        dataSources=base_dict_to_entity_dict(
            base_entities, b.EntityType.DATA_SOURCES
        ),
        # dataSources=base_entity_dict_to_wrapper_dict[ds.DataSource](base_entities, b.EntityType.DATA_SOURCES),
        folders={},  # base_dict_to_entity_dict(base_entities, b.EntityType.FOLDERS),
        # folders=base_entity_dict_to_wrapper_dict[f.Folder](base_entities, b.EntityType.FOLDERS),
        modelEntities=model_entities,
    )

    executor.shutdown()

    logger.info("Parsed all files in solution")

    return model


def base_dict_to_entity_dict(d, t):
    return {
        _entity.name: EntityWrapper(
            model_object=_entity,
            locator=Locator(
                entityType=t.value,
                folders=[],
                entityName=_entity.name,
            ),
        )
        for _entity in d[t]
    }


def __compose_locator(path: str) -> Locator:
    parts = path.removesuffix(".json").split("/")
    parts.remove("")
    locator = Locator(
        entityType=parts[0],
        folders=parts[1:-1],
        entityName=parts[-1],
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
