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

"""
Helpers to resolve, read and update the functions behind model transformations.

A function is the source code of a model transformation, stored in a file next to
the entity definition. This module provides lookups by step number and/or name as
well as reading and writing of the corresponding source files.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, SkipValidation

from datam8 import logging
from datam8.model import EntityWrapper, Locator
from datam8_model import model as m

__all__ = ["get_functions", "get_function", "update_function", "Function"]
logger = logging.getLogger(__name__)


def _build_source_file_path(
    wrapper: EntityWrapper[m.ModelEntity], transformation: m.ModelTransformation
) -> Path:
    assert transformation.function is not None
    return (wrapper.source_file.parent / transformation.function.source).resolve()


def get_functions(wrapper: EntityWrapper[m.ModelEntity], /) -> list[Function]:
    """
    Get all functions of the transformations of a model entity.

    Parameters
    ----------
    wrapper : `EntityWrapper[ModelEntity]`
        The wrapper of the entity to get the functions from.

    Returns
    -------
    `list[Function]`
        The functions of all transformations of the entity.
    """
    assert isinstance(wrapper.entity, m.ModelEntity)
    return [get_function(wrapper, func.stepNo) for func in wrapper.entity.transformations]


def get_function(wrapper: EntityWrapper[m.ModelEntity], /, step_no_or_name: int | str) -> Function:
    """
    Get a single function of a model entity by step number and/or name.

    Parameters
    ----------
    wrapper : `EntityWrapper[ModelEntity]`
        The wrapper of the entity owning the function.
    step_no : `int | None`
        The step number of the transformation. At least `step_no` or `name` must be provided.
    name : `str | None`, optional
        The name of the transformation function.

    Returns
    -------
    `Function`
        The resolved function.

    Raises
    ------
    ValueError
        If neither `step_no` nor `name` is provided or if no unique function is found.
    NotImplementedError
        If the matching transformation is not of kind `FUNCTION`.
    """
    assert isinstance(wrapper.entity, m.ModelEntity)

    possible_functions = [
        func
        for func in wrapper.entity.transformations
        if isinstance(step_no_or_name, int)
        and func.stepNo == step_no_or_name
        or isinstance(step_no_or_name, str)
        and func.name == step_no_or_name
    ]

    if len(possible_functions) != 1:
        raise ValueError(
            f"No unique function found for the provided step or name: {step_no_or_name}"
        )
    else:
        transformation = possible_functions[0]

    if transformation.kind == m.TransformationKind.FUNCTION:
        assert (
            # defined by json schema if it is a function
            transformation.function is not None
        )

        source_file_path = _build_source_file_path(wrapper, possible_functions[0])
    else:
        raise NotImplementedError(
            f"Transformations of type {transformation.kind.value} are not implemented."
        )

    return Function.from_path(wrapper.locator, source_file_path, transformation)


def update_function(
    wrapper: EntityWrapper[m.ModelEntity],
    /,
    step_no_or_name: int | str,
    content: str,
) -> None:
    """
    Update the source code of a transformation function of a model entity.

    The updated source code is written back to the function's source file.

    Parameters
    ----------
    wrapper : `EntityWrapper[ModelEntity]`
        The wrapper of the entity owning the function.
    step_no : `int | None`
        The step number of the transformation. At least `step_no` or `name` must be provided.
    content : `str`
        The new source code of the function.
    name : `str | None`, optional
        The name of the transformation function.
    """
    func = get_function(wrapper, step_no_or_name)
    func.source_code = content
    func.to_path(_build_source_file_path(wrapper, func.transformation))


def move_function(
    wrapper: EntityWrapper[m.ModelEntity],
    transformation: m.ModelTransformation,
    /,
    new_path: Path,
    *,
    force: bool = False,
) -> None:
    assert transformation.kind == m.TransformationKind.FUNCTION
    assert transformation.function is not None

    current_path = _build_source_file_path(wrapper, transformation)

    new_path = new_path.resolve()
    new_path_relative = new_path.relative_to(wrapper.source_file.parent, walk_up=True)

    if current_path == new_path:
        raise FileExistsError("Trying to move function onto itself")

    if new_path.exists() and not force:
        raise FileExistsError("Target function file already exists")

    new_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.replace(new_path)

    # update the wrapper so that is marked for change
    transformation.function.source = new_path_relative.as_posix()
    wrapper._changed = True


def prepare_function_moves(
    wrapper: EntityWrapper[m.ModelEntity],
    /,
    new_path: Path,
    *,
    force: bool = False,
    source_file_overwrite: Path | None = None,
) -> list[FunctionMove]:
    """
    Prepares and validates from where to where functions need to be moved for specific wrapper. This
    allows to separately prepare and actually move the functions.

    Additionally, this allows to provide a different wrapper when executing the move, which is
    neceddary to calculate the correct relative paths when the whole entity is being moved.
    """
    if new_path.is_file():
        raise ValueError(
            "When moving all transformations for an entity, `new_path` cannot be a file"
        )

    source_file_directory = wrapper.source_file.parent

    to_move = [
        FunctionMove(
            transformation,
            # absolute path from where the function will be moved
            src=(source_file_directory / transformation.function.source).resolve(),
            # absolute path to where the function will be moved, will be None if the src is located
            # "above" the entity itself
            trg=(new_path / transformation.function.source).resolve()
            # only functions that are located right beside or below the model entity file should be
            # moved, assuming that every other functions in higher directories are "shared" or reusable
            # functions, so do not move those simply update the relative source path and be done with it
            if (source_file_directory / transformation.function.source)
            .resolve()
            .is_relative_to(source_file_directory)
            else None,
        )
        for transformation in wrapper.entity.transformations
        if transformation.function is not None
    ]

    # in case a non-builtin transformation already exists raise an error
    # non-builtins will not be moved, so can be ignored
    existing_transformations = [
        mv
        for mv in to_move
        if mv.transformation.kind != m.TransformationKind.BUILTIN
        and mv.trg is not None
        and mv.trg.exists()
    ]
    if not force and len(existing_transformations) > 0:
        raise FileExistsError(
            "One of the transformations to be moved already exists: "
            + ", ".join([mv.src.resolve().as_posix() for mv in existing_transformations])
        )

    # in case the wrapper source file path was overwritten, adapt the transformation function
    # sources to be relative to the overwrite loation, NOT the input wrapper location
    if source_file_overwrite is not None:
        for t, src, _ in to_move:
            if t.function is not None and t.kind == m.TransformationKind.FUNCTION:
                t.function.source = src.relative_to(
                    source_file_overwrite.parent, walk_up=True
                ).as_posix()

    logger.debug("Detected %s functions to move for '%s'", len(to_move), wrapper.locator)

    return to_move


def move_functions(
    wrapper: EntityWrapper[m.ModelEntity],
    /,
    new_path: Path,
    *,
    force: bool = False,
    to_move: list[FunctionMove] | None = None,
) -> None:
    """
    Move all functions of a specific model entity to a new directory.

    This will prepare and validate the possible functions to move. Optionally, provide a
    pre-validated list of :class:`FunctionMove` objects that will be execute relative to the
    provided wrapper.
    """
    to_move = prepare_function_moves(wrapper, new_path, force=force) if to_move is None else to_move
    result: list[str | None] = [None for _ in range(len(to_move))]

    for idx, (t, _, trg) in enumerate(to_move):
        if trg is None and t.function is None:
            result[idx] = "skipped - not a function"
        elif trg is None:
            result[idx] = f"shared transformation - updated path to {trg}"
        else:
            move_function(wrapper, t, new_path=trg, force=force)
            result[idx] = f"moved to {trg}"

    for idx, r in enumerate(result):
        logger.debug("%s. %s: %s", idx, to_move[idx][0].name, r)

    logger.info("Moved %s functions", len([s for s in result if s == "moved"]))


class FunctionMove(NamedTuple):
    transformation: m.ModelTransformation
    src: Path
    "This is mostly informative and for calculation purposes"
    trg: Path | None
    "If trg is None this move will be a simple path update, no file will actually be moved"


class Function(BaseModel):
    """
    The source code of a transformation function together with its source file
    path and the transformation it belongs to.
    """

    locator: Locator
    source_file_path: Path
    source_code: str
    transformation: SkipValidation[m.ModelTransformation]
    """
    Skip validation as that creates a new pydantic object, but we need a reference to the original
    object. The validation is also already done when reading the model file from disk or when it is
    being updated.
    """

    @classmethod
    def from_path(
        cls, locator: Locator, path: Path, transformation: m.ModelTransformation
    ) -> Function:
        """
        Create a `Function` by reading the source code from a file.

        Parameters
        ----------
        path : `pathlib.Path`
            The path to the source file to read.
        func : `datam8_model.model.ModelTransformation`
            The transformation the function belongs to.

        Returns
        -------
        `Function`
            The created function.
        """
        with open(path, encoding="UTF-8") as file:
            content = file.read()

        return Function(
            locator=locator,
            source_file_path=path,
            source_code=content,
            transformation=transformation,
        )

    def to_path(self, path: Path) -> None:
        """
        Write the source code of the function to a file.

        Parameters
        ----------
        path : `pathlib.Path`
            The path of the file to write the source code to.
        """
        with open(path, mode="w", encoding="UTF-8") as file:
            file.write(self.source_code)
