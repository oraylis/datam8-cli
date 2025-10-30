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

import asyncio
import pathlib
import sys
from collections.abc import Sequence
from concurrent import futures

from pydantic_core import ValidationError

from dm8model.property import PropertyReference

from . import config, model, model_exceptions, parser, parser_exceptions, utils

logger = utils.start_logger(__name__)

_model: model.Model


@utils.get_logger
def create_model(solution_path: pathlib.Path | None = None) -> model.Model:
    global _model

    path = solution_path or config.solution_path

    if not path.exists():
        logger.error("Solution file does not exists")
        sys.exit(1)

    try:
        _model = asyncio.run(parser.parse_full_solution_async(path))

        if not config.lazy:
            _resolve_model_properties(_model)

    except ValidationError as err:
        logger.error(err)
        sys.exit(1)
    except parser_exceptions.ModelParseException as err:
        logger.error(err)
        sys.exit(1)
    except parser_exceptions.NotSupportedModelVersion as err:
        logger.error(err)
        logger.warning(f"Supported versions are: {config.supported_model_versions}")
        sys.exit(1)
    except model_exceptions.EntityNotFoundError as err:
        logger.error(err)
        sys.exit(1)
    except model_exceptions.PropertiesNotResolvedError as err:
        logger.error(err)
        sys.exit(1)

    # TODO: reference resolution

    return _model


def _resolve_model_properties(_model: model.Model) -> None:
    executor = futures.ThreadPoolExecutor()

    executor.map(_resolve_wrapper_properties, _model.get_entity_iterator())


def _resolve_wrapper_properties(wrapper: model.EntityWrapper) -> None:
    entity = wrapper.entity
    if hasattr(entity, "properties"):
        if entity.properties is not None:
            _resolve_properties(wrapper, entity.properties)


def _resolve_properties(
    wrapper: model.EntityWrapper, properties: Sequence[PropertyReference]
) -> None:
    if len(properties) == 0:
        return

    global _model
    _properties = [
        model.PropertyReference(property=pr.property, value=pr.value) for pr in properties
    ]

    logger.debug(
        "%s - %s", wrapper.locator, [f"{p.property}:{p.value}" for p in properties]
    )

    for ref in _properties:
        property_value = _model.get_property_value(ref.property, ref.value)
        wrapper._properties[property_value.locator] = property_value.entity

        if property_value.entity.properties:
            _resolve_properties(wrapper, property_value.entity.properties)

    wrapper.resolved = True
