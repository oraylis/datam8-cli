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

from pydantic_core import ValidationError

from datam8_model import folder as f
from datam8_model.property import PropertyReference, PropertyValue

from . import config, model, model_exceptions, parser, parser_exceptions, utils

logger = utils.start_logger(__name__)

_model: model.Model


@utils.get_logger
def create_model(solution_path: pathlib.Path | None = None) -> model.Model:
    """Create model.

    Parameters
    ----------
    solution_path : pathlib.Path | None
        solution_path parameter value.

    Returns
    -------
    model.Model
        Computed return value."""
    global _model

    path = solution_path or config.solution_path

    if not path.exists():
        logger.error("Solution file does not exists")
        sys.exit(1)

    try:
        _model = asyncio.run(parser.parse_full_solution_async(path))

        create_undefined_folders(_model)

        if not config.lazy:
            _model.resolve()

    except RecursionError as err:
        logger.error(err)
        sys.exit(1)
    except ValidationError as err:
        logger.error(err)
        sys.exit(1)
    except parser_exceptions.ModelParseException as err:
        logger.error(err)
        sys.exit(1)
    except parser_exceptions.NotSupportedModelVersion as err:
        logger.error(err)
        logger.warning(f"Supported versions are: {config.supported_model_versions}")

        if err.version == "1.0.0":
            logger.warning(f"Supported versions are: {config.supported_model_versions}")

        sys.exit(1)
    except model_exceptions.EntityNotFoundError as err:
        logger.error(err)
        sys.exit(1)
    except model_exceptions.PropertiesNotResolvedError as err:
        logger.error(err)
        sys.exit(1)

    return _model


def resolve_property(
    model: model.Model, reference: PropertyReference
) -> list[PropertyValue]:
    """
    Lookup and Resolve a single PropertyReference. Useful to resolve properties that are not
    set directly on the entity, e.g. a property on an attribute.

    Parameters
    ----------
    model : `Model`
        The DataM8 Model that will be used to lookup the PropertyReference
    reference : `PropertyReference`
        The PropertyReference, i.e. property-value-pair, that will be recursively resolved
        with the provided model.

    Returns
    -------
    list[PropertyValue]
        A list of all properties that are related to the provided reference. The PropertyValue
        includes all custom attributes.
    """
    properties: list[PropertyValue] = []

    for pv in model.propertyValues.values():
        if (pv.entity.property, pv.entity.name) != (reference.property, reference.value):
            continue

        properties.append(pv.entity)

        for nested_ref in pv.entity.properties or []:
            properties.extend(resolve_property(model, nested_ref))

        # early exit of loop if match was found
        break

    return properties


def create_undefined_folders(_model: model.Model):
    """
    Goes through all model entities and adds folder wrappers for every parent locator
    of an entity that does not exist yet.

    Folder IDs are simply sequential increased during runtime.

    Parameters
    ----------
    _model : `model.Model`
        A fully parsed DataM8 folder. Can be run pre or post property resolution.
    """
    existing_folders = [w.entity.id for w in _model.folders.values()]
    next_id = (max(existing_folders) if len(existing_folders) != 0 else 0) + 1

    undefined_folders: model.EntityDict[f.Folder] = {}

    for wrapper in _model.get_entity_iterator():
        loc = wrapper.locator
        for ploc in loc.parents:
            if ploc in _model.folders or ploc.entityName is None:
                continue

            undefined_folders[ploc] = model.EntityWrapper(
                locator=ploc,
                entity=f.Folder(
                    id=next_id,
                    name=ploc.entityName,
                ),
            )

            next_id += 1

    for loc in undefined_folders:
        if loc not in _model.folders:
            _model.folders[loc] = undefined_folders[loc]
