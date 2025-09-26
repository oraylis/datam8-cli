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

from . import config, model_exceptions, parser, parser_exceptions, utils
from .model import Model

logger = utils.start_logger(__name__)

_model: Model


def create_model(solution_path: pathlib.Path | None = None) -> Model:
    global _model

    path = solution_path or config.solution_path

    if not path.exists():
        logger.error("Solution file does not exists")
        sys.exit(1)

    try:
        _model = asyncio.run(parser.parse_full_solution_async(path))
        # if not config.lazy:
        #     __resolve_model_properties(_model)

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


# def __resolve_wrapper_properties(
#     model: Model, wrapper: EntityWrapper[BaseEntityType]
# ) -> None:
#     for ref in wrapper.entity.properties:
#         result_set = [
#             pv
#             for pv in model.propertyValues.values()
#             if pv.entity.name == ref.value
#             and pv.entity.property == ref.property
#         ]
#
#         if len(result_set) != 1:
#             raise parser.ModelParseException(
#                 msg=f"PropertyReference could not be resolved to one PropertyValue {ref}"
#             )
#
#         wrapped_property_value = result_set.pop()
#
#         if wrapped_property_value.entity.properties:
#             __resolve_wrapper_properties(model, wrapped_property_value)
#
#         logger.info(wrapped_property_value)
#
#         wrapper.properties[PropertyReference.from_model_ref(ref)] = (
#             wrapped_property_value
#         )
#
#
# def __resolve_model_properties(model: Model) -> None:
#     for folder in model.folders.values():
#         if folder.entity.properties is None:
#             continue
#
#         __resolve_wrapper_properties(model, folder)

# def __get_single_property_value(
#     self, ref: p.PropertyReference
# ) -> p.PropertyValue:
#     results = [
#         pv
#         for pv in self.propertyValues.values()
#         if pv.model_object.name == ref.value
#         and pv.model_object.property == ref.property
#     ]

#     if len(results) != 1:
#         raise Exception(
#             f"The requested property value is not or multiple times defined {ref}"
#         )

#     return results.pop().model_object

# def get_nested_properties(
#     self, reference: p.PropertyReference
# ) -> Sequence[p.PropertyValue]:
#     return []

# # def get_property(self, ref: p.PropertyReference) -> Sequence[p.PropertyValue]

# def get_property_values(
#     self, references: Sequence[p.PropertyReference]
# ) -> Sequence[p.PropertyValue]:
#     result_set: Sequence[p.PropertyValue] = []

#     for ref in references:
#         result_set.append(self.__get_single_property_value(ref))
#         self.get_nested_properties(ref)

#     return result_set
