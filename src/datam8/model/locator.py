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

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from datam8 import errors, utils
from datam8_model import base as b
from datam8_model import model as m

type LocatorOrString = Locator | str


def _ensure_locator(locator: str | Locator) -> Locator:
    if isinstance(locator, str):
        return Locator.from_path(locator)

    return locator


class Locator(m.Locator):
    """
    Sub-class of `datam8.model.Locator` offerting further functionality.
    Should be used instead of its base class.
    """

    def __init__(self, entityType: str, folders: Iterable[str], entityName: str | None = None):
        super().__init__(entityType=entityType, folders=folders, entityName=entityName)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other

        if not isinstance(other, Locator):
            raise utils.create_error(
                TypeError(f"Cannot compare object of type {type(other)} with Locator")
            )

        return all(
            [
                self.entityType == other.entityType,
                self.folders == other.folders,
                self.entityName == other.entityName,
            ]
        )

    def __contains__(self, other: object) -> bool:
        # ensure later checks are only done on locator objects
        if isinstance(other, str):
            other = Locator.from_path(other)
        elif not isinstance(other, Locator):
            raise utils.create_error(
                TypeError(f"Cannot compare object of type {type(object).__name__} with Locator")
            )

        if self == other or self == ROOT_LOCATOR:
            return True

        # basic format checks before comparison the actual folder paths
        if (
            self.entityName is not None
            or self == other
            or self.entityType != other.entityType
            or len(self.folders) > len(other.folders)
        ):
            return False

        left_path = Path("/".join(other.folders))
        right_path = Path("/".join(self.folders))

        return left_path.is_relative_to(right_path)

    def __hash__(self):
        return hash(self.__str__())

    def __str__(self) -> str:
        parts = [self.entityType, *self.folders]
        if self.entityName is not None:
            parts.append(self.entityName)
        return "/".join(parts)

    def __repr__(self) -> str:
        return f"Locator(entityType={self.entityType} folder={self.folders} entityName={self.entityName})"

    def clone(self) -> Locator:
        return Locator(
            entityType=self.entityType,
            folders=self.folders,
            entityName=self.entityName,
        )

    def clone_as(self, entity_type: b.EntityType | str) -> Locator:
        """Creates a clone of the locator and changes the entityType."""
        new = self.clone()
        new.entityType = b.EntityType(entity_type).value
        return new

    @staticmethod
    def from_path(path: str | Path, /) -> Locator:
        """
        Creates a Locator object based on the given path.
        Trailing `.json` suffixes will be removed.

        Examples
        -------
        * `/modelEntities/raw/sales/other/Customer.json` resolves to
          - type: `"modelEntities"`
          - folders: `["raw", "sales", "other"]`
          - entityName: `"Customer"`
        * `/dataSources/AdventureWorks` resolves to
          - type: `"dataSources"`
          - folders: `[]`
          - entityName: `"AdventureWorks"`
        * `/properties/tags/` resolves to
          - type: `"properties"`
          - folders: `["tags"]`
          - entityName: `None`

        Parameters
        ----------
        path : `str` | `Path`
            Physical or logical Path of a file/entity within the solution.

        Returns
        -------
        `Locator`
            An identifier unique for every object in the solution.
        """
        path_ = path if isinstance(path, str) else path.as_posix()

        if path_ == "/":
            return ROOT_LOCATOR

        parts = path_.removesuffix(".json").removeprefix("/").split("/")

        if any(
            [
                len(parts) < 1,
                parts[0] not in [member.value for member in b.EntityType],
            ]
        ):
            raise utils.create_error(errors.InvalidLocatorError(path_))

        if len(parts) == 1:
            locator = Locator(entityType=parts[0], folders=[], entityName=None)
        else:
            locator = Locator(
                entityType=parts[0],
                folders=parts[1:-1],
                entityName=None if parts[-1] == "" else parts[-1],
            )

        return locator

    @property
    def parent(self) -> Locator | None:
        "Get the parent folder of this entity."

        if len(self.folders) < 1 and self.entityName is None:
            return None

        if len(self.folders) < 1:
            return Locator(entityType=self.entityType, folders=[])

        new_folders = self.folders[:-1]
        entity_name = self.folders[-1]

        ploc = Locator(
            entityType=b.EntityType.FOLDERS.value,
            folders=new_folders,
            entityName=entity_name,
        )

        return ploc

    @property
    def parents(self) -> Iterator[Locator]:
        "Returns all parent folders for this locator."

        current = self

        while (parent := current.parent) is not None:
            yield parent
            current = parent

    def without_type(self) -> str:
        """
        Returns the locator as a string without the type

        Examples
        --------
        >>> Locator.from_path("modelEntities/test").without_type()
        "test"
        """
        return f"{'/'.join(self.folders)}/{self.entityName}"

    def default_file_name(self) -> str:
        assert self.entityName is not None
        type_ = b.EntityType(self.entityType)

        if type_ == b.EntityType.FOLDERS:
            return ".properties.json"

        if type_ == b.EntityType.MODEL_ENTITIES:
            return f"{self.entityName}.json"

        # capitalize the first letter
        # e.g. propertyValues -> PropertyValues
        capitalized_first_letter = self.entityType[0].upper() + self.entityType[1:]

        return f"{capitalized_first_letter}.json"

    def rebase(self, onto: Locator) -> Locator | None:
        """
        Rebase a locator onto another locator. Works similar to git rebase.

        Examples
        --------
        >>> Locator("T", ["A"], "A").rebase(Locator("T", ["B", "B"], "B"))
        ... Locator("T", ["B", "B", "A"], "A")

        >>> Locator("T", ["C"], "C").rebase(Locator("T", ["C", "D"], "D"))
        ... Locator("T", ["C", "D"], "C")

        Returns
        -------
        `None`
            If the locator cannot be rebased.
        :class:`Locator`
            If the locator could be rebased.
        """
        if onto == ROOT_LOCATOR:
            return self.clone()

        if self.entityType != onto.entityType:
            return None

        target = Path("/", *onto.folders)
        source = Path("/", *self.folders)
        new_folders = []

        for p in [source, *source.parents]:
            if target.is_relative_to(p):
                return Locator(self.entityType, [*onto.folders, *new_folders], self.entityName)
            else:
                new_folders.insert(0, p.stem)

    def relative_to(self, to_: Locator) -> Path:
        """
        Raises
        ------
        RuntimeError
            if `to_` is not a parent
        """
        return Path(str(self)).relative_to(str(to_))


ROOT_LOCATOR = Locator(entityType="/", folders=[], entityName=None)
