"""
This module handles all parsing of json files into generator internal objects.
"""

import pathlib
from concurrent import futures
from typing import Any

from pydantic import ValidationError

from dm8gen import config
from dm8gen.model import (
    EntityWrapper,
    Model,
    EntityDict,
    Locator,
    new_empty_base_entity_dict,
    wrap_base_entity,
)
from dm8model import base as b
from dm8model import model as m
from dm8model import solution as s

from . import utils

logger = utils.start_logger(__name__)


@utils.print_progress_async("Parsing files...")
@utils.get_logger
async def parse_full_solution_async(solution_path: pathlib.Path) -> Model:
    """Load and parses all json files in a solution into generator internal objects.

    Executes loading & parsing of json files via multi threading.

    Parameters
    ----------
    solution_path : `Path`
        path to the solution file (.dm8s)
    lazy : `bool`
        if lazy loading is enabled model entities will not be loaded, which
        needs to be handeled afterwards on the fly.

    Returns
    -------
    Model
        The parsed model from files BUT not validated in regards to internal
        references, e.g. PropertyReferences.
    """
    logger.debug("Start parsing solution")

    executor = futures.ThreadPoolExecutor()

    solution = __parse_solution_file(solution_path)
    worker_model = executor.submit(__parse_model_entities, solution.modelPath)
    worker_base = executor.submit(
        __parse_base_entities, solution.basePath, solution.modelPath
    )

    base_entities = worker_base.result()
    model_entities = worker_model.result()

    model = Model(
        solution=solution,
        modelEntities=model_entities,
        **base_entities,
    )

    executor.shutdown()

    logger.info("Parsed all files in solution")

    return model


def __parse_base_entity_type(entity_type: str) -> b.EntityType:
    return {e.value: e for e in b.EntityType}[entity_type]


def __parse_solution_file(path: pathlib.Path) -> s.Solution:
    solution = s.Solution.from_json_file(path)
    logger.info(
        f"Parsed solution file with schema version: {solution.schemaVersion}",
    )
    logger.debug(solution.model_dump_json(indent=4))
    return solution


def __parse_model_entities(
    path: pathlib.Path,
    executor: futures.ThreadPoolExecutor | None = None,
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

    if executor is None:
        _executor = futures.ThreadPoolExecutor()
    else:
        _executor = executor

    loaded_entities = _executor.map(__parse_model_entity_file, model_files)

    for rel_path, model_entity_or_err in loaded_entities:
        if isinstance(model_entity_or_err, ValidationError):
            parse_errors[rel_path] = model_entity_or_err
            continue

        clean_path = rel_path.as_posix().removeprefix(path.as_posix())
        locator = Locator.from_path(
            f"{b.EntityType.MODEL_ENTITIES.value}/{clean_path}"
        )
        model_entities[locator] = EntityWrapper[m.ModelEntity](
            locator=locator,
            entity=model_entity_or_err,
        )

    if executor is None:
        _executor.shutdown()

    if parse_errors:
        raise ModelParseException(
            inner_exceptions=[err for err in parse_errors.values()]
        )

    logger.info(f"Parsed model entities: {len(model_files)}")

    return model_entities


def __parse_model_entity_file(
    path: pathlib.Path,
) -> tuple[pathlib.Path, m.ModelEntity | ValidationError]:
    rel_path = path.relative_to(config.solution_folder_path)

    try:
        model_entity = m.ModelEntity.from_json_file(path)
    except ValidationError as err:
        logger.error(f"{path}: \n{err}")
        return rel_path, err

    logger.debug(rel_path)

    return rel_path, model_entity


def __parse_base_entities(
    base_path: pathlib.Path,
    model_path: pathlib.Path,
    executor: futures.ThreadPoolExecutor | None = None,
) -> dict[str, EntityDict[Any]]:
    logger.debug(f"Scanning {base_path} for base entities")
    logger.debug(f"Scanning {model_path} for folder entities")

    base_files = [
        *(config.solution_folder_path / base_path).glob("**/*.json"),
        *(config.solution_folder_path / model_path).glob("**/.properties.json"),
    ]

    _executor = executor or futures.ThreadPoolExecutor()

    # ensure every entity type except modelEntities is present in dictionary
    base_entities = new_empty_base_entity_dict()
    del base_entities[b.EntityType.MODEL_ENTITIES]

    loaded_entities = _executor.map(__parse_base_entity_file, base_files)
    parse_errors: dict[pathlib.Path, ValidationError] = {}

    for rel_path, base_entity_list_or_err in loaded_entities:
        if isinstance(base_entity_list_or_err, ValidationError):
            parse_errors[rel_path] = base_entity_list_or_err
            continue

        entity_type, entity_list = base_entity_list_or_err
        for entity in entity_list:
            base_entities[entity_type].append(
                wrap_base_entity(entity_type, pathlib.Path(), entity)
            )

    if executor is None:
        _executor.shutdown()

    if parse_errors:
        raise ModelParseException(
            inner_exceptions=[err for err in parse_errors.values()]
        )

    logger.info(
        f"Parsed base entities: {sum([len(x) for x in base_entities.values()])}"
    )

    unpacked_entities = {
        k.value: {
            wrapped_entity.locator: wrapped_entity for wrapped_entity in v
        }
        for k, v in base_entities.items()
    }

    return unpacked_entities


def __parse_base_entity_file(
    path: pathlib.Path,
) -> tuple[
    pathlib.Path, tuple[b.EntityType, list[b.BaseEntityType]] | ValidationError
]:
    rel_path = path.relative_to(config.solution_folder_path)

    try:
        base_entities = b.BaseEntities.from_json_file(path)
    except ValidationError as err:
        logger.error(f"{path}: \n{err}")
        return rel_path, err

    entities_type = __parse_base_entity_type(base_entities.root.type)
    entities = getattr(base_entities.root, entities_type.value)

    logger.debug(rel_path)

    return rel_path, (entities_type, entities)


class ModelParseException(Exception):
    def __init__(
        self,
        msg="Error(s) occured during model files parsing.",
        inner_exceptions: list[Exception] = [],
    ):
        Exception.__init__(self, msg)

        self.inner_exceptions = inner_exceptions
        self.message = msg
