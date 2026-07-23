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

import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, cast, overload

from pydantic import ConfigDict, Field, ValidationError

from datam8 import config, errors, logging, opts, utils
from datam8_model import attribute as a
from datam8_model import base as b
from datam8_model import data_product as dp
from datam8_model import data_source as ds
from datam8_model import data_type as dt
from datam8_model import folder as f
from datam8_model import model as m
from datam8_model import property as p
from datam8_model import solution as s
from datam8_model import zone as z

from .entity_wrapper import EntityRepository, EntityWrapper, EntityWrapperVariant
from .locator import ROOT_LOCATOR, Locator, LocatorOrString, _ensure_locator

logger = logging.getLogger(__name__)

MODEL_DUMP_OPTIONS: dict[str, Any] = {
    "indent": 2,
    "exclude_defaults": True,
    "exclude_none": True,
}


def class_from_type(_type: b.EntityType) -> type[b.BaseEntityType]:
    match _type:
        case b.EntityType.PROPERTIES:
            _class = p.Property
        case b.EntityType.PROPERTY_VALUES:
            _class = p.PropertyValue
        case b.EntityType.ZONES:
            _class = z.Zone
        case b.EntityType.MODEL_ENTITIES:
            _class = m.ModelEntity
        case b.EntityType.FOLDERS:
            _class = f.Folder
        case b.EntityType.DATA_TYPES:
            _class = dt.DataTypeDefinition
        case b.EntityType.DATA_SOURCES:
            _class = ds.DataSource
        case b.EntityType.DATA_SOURCE_TYPES:
            _class = ds.DataSourceType
        case b.EntityType.DATA_PRODUCTS:
            _class = dp.DataProduct
        case b.EntityType.DATA_MODULES:
            _class = dp.DataModule
        case b.EntityType.ATTRIBUTE_TYPES:
            _class = a.AttributeType

    return _class


def _default_base_file_name_for_type(_type: b.EntityType) -> str:
    names = {
        b.EntityType.PROPERTIES: "Properties.json",
        b.EntityType.PROPERTY_VALUES: "PropertyValues.json",
        b.EntityType.ZONES: "Zones.json",
        b.EntityType.DATA_TYPES: "DataTypes.json",
        b.EntityType.DATA_SOURCE_TYPES: "DataSourceTypes.json",
        b.EntityType.DATA_PRODUCTS: "DataProducts.json",
        b.EntityType.DATA_MODULES: "DataModules.json",
        b.EntityType.ATTRIBUTE_TYPES: "AttributeTypes.json",
        b.EntityType.DATA_SOURCES: "DataSources.json",
    }
    return names.get(_type, f"{_type.value}.json")


class PropertyReference(p.PropertyReference):
    """
    Sub-class of `datam8.property.PropertyReference` for actual use with the
    generator offering further functionality.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, p.PropertyReference):
            return self.property == other.property and self.value == other.value
        elif not isinstance(other, PropertyReference):
            return False

        return self.property == other.property and self.value == other.value

    def __hash__(self):
        return hash((self.property, self.value))

    @staticmethod
    def from_model_ref(ref: p.PropertyReference, /):
        """
        Converts a PropertyReference parsed from a json file into the
        internally used one.

        # Parameters
        ----------
        ref : `datam8_model.property.PropertyReference`
            Reference to a property value, directly parsed from the json files.
        """
        return PropertyReference(
            property=ref.property,
            value=ref.value,
        )


class Model:
    """
    The main class that all data from the datam8 solution will be stored in.

    It will also be the main interface for use in templates. Nothing else should
    be available there directly.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )
    solution: Annotated[s.Solution, Field(frozen=True)]
    properties: EntityRepository[p.Property]
    propertyValues: EntityRepository[p.PropertyValue]
    zones: EntityRepository[z.Zone]
    dataTypes: EntityRepository[dt.DataTypeDefinition]
    dataSources: EntityRepository[ds.DataSource]
    dataSourceTypes: EntityRepository[ds.DataSourceType]
    dataProducts: EntityRepository[dp.DataProduct]
    attributeTypes: EntityRepository[a.AttributeType]
    folders: EntityRepository[f.Folder]
    modelEntities: EntityRepository[m.ModelEntity]
    lock = Lock()

    def __init__(self, solution: s.Solution, /, **kwargs: EntityRepository[b.BaseEntityType]):
        self.solution = solution

        for k, v in kwargs.items():
            v.model = self
            setattr(self, k, v)

        self._model_files: dict[Path, EntityFileRef] = {}
        """Internal dictionary to allow easy mapping of files and their entities"""

        if len(self.modelEntities) == 0:
            self.__next_model_id = 1
        else:
            self.__next_model_id = max(
                wrapper.entity.id for wrapper in self.modelEntities.values()
            ) + 1

    def __getitem__(self, type_: str) -> EntityRepository[b.BaseEntityType]:
        return getattr(self, type_)

    def get_next_model_id(self) -> int:
        with self.lock:
            next = self.__next_model_id
            self.__next_model_id += 1
        return next

    def init_file_references(self) -> None:
        self._model_files = {}

        for _wrapper in self.get_entity_iterator():
            if _wrapper.source_file not in self._model_files:
                self._model_files[_wrapper.source_file] = EntityFileRef(
                    _type=b.EntityType(_wrapper.locator.entityType), file_path=_wrapper.source_file
                )

            self._model_files[_wrapper.source_file].locators.append(_wrapper.locator)

    def update_file_reference(
        self, *, _type: b.EntityType, file_path: Path, locators: list[Locator] | None = None
    ) -> None:
        if file_path not in self._model_files:
            logger.debug(f"Adding new file ref for {file_path}")
            self._model_files[file_path] = EntityFileRef(_type, file_path)

        if locators is not None and len(locators) > 0:
            logger.debug(f"Adding {locators} to {file_path}")
            self._model_files[file_path].locators.extend(locators)

    def resolve_wrapper[T: b.BaseEntityType](
        self, wrapper: EntityWrapper[T], /
    ) -> EntityWrapper[T]:
        """
        Recursively lookup concrete property value objects and write them to
        `EntityWrapper.properties`

        Parameters
        ----------
        model : `model.Model`
            The DataM8 model to lookup up the property values. This normally is the same
            model as the one this EntityWrapper resides in, but could also be a separate model.

        Returns
        -------
        `EntityWrapper[T]`
            The resolved entity itself.
        """
        if wrapper.resolved:
            logger.warning(
                "Tried resolving an already resolved entity, this should not be done"
                f" - {wrapper.locator}"
            )
            return wrapper

        if not hasattr(wrapper.entity, "properties"):
            wrapper.resolved = True
            return wrapper

        property_references: list[p.PropertyReference] = list(
            getattr(wrapper.entity, "properties", None) or []
        )
        property_references += [
            pr
            for pr in self.get_inherited_property_references(wrapper)
            # NOTE: properties set on the entity itself takes precedene to
            # inherited properties
            if pr not in property_references
        ]

        if len(property_references) > 0:
            self._resolve_properties(wrapper, property_references)

        self._resolve_model_attributes(wrapper)
        wrapper.resolved = True

        logger.info("Resolved %s", str(wrapper.locator))

        return wrapper

    def _resolve_model_attributes[T: b.BaseEntityType](self, wrapper: EntityWrapper[T], /) -> None:
        if not isinstance(wrapper.entity, m.ModelEntity):
            return

        for attr in wrapper.entity.attributes:
            pass
            # logger.error(attr.properties)

    def resolve(self) -> None:
        "Resolve all entities by iterating over them."
        for wrapper in self.get_entity_iterator():
            if not wrapper.resolved:
                self.resolve_wrapper(wrapper)  # pyright: ignore[reportArgumentType]

    def get_inherited_property_references[T: b.BaseEntityType](
        self, wrapper: EntityWrapper[T], /
    ) -> list[p.PropertyReference]:
        """
        Get a distinct list of properties of parent Entities (most likely foldres).

        Returns
        -------
        `list[PropertyReference]`
            A list of PropertyReference of parent locators. They are not yet resolved recursively.
        """
        parent_properties: list[p.PropertyReference] = []

        for parent in wrapper.locator.parents:
            if parent not in self.folders:
                continue

            parent_folder = self.folders[parent].entity

            if not parent_folder.properties:
                continue

            parent_properties.extend(
                iter([pr for pr in parent_folder.properties if pr not in parent_properties])
            )

        # in case the entity is a model also get the zones properties
        if wrapper.locator.entityType == b.EntityType.MODEL_ENTITIES.value:
            zone = self.get_zone_for_entity(
                cast(EntityWrapper[m.ModelEntity], wrapper)
            )
            if not zone.resolved:
                self.resolve_wrapper(zone)

            if zone.entity.properties is not None:
                parent_properties.extend(
                    iter([pr for pr in zone.entity.properties if pr not in parent_properties])
                )

        return parent_properties

    def _resolve_properties[T: b.BaseEntityType](
        self, wrapper: EntityWrapper[T], /, properties: Sequence[p.PropertyReference]
    ) -> None:
        """
        Recursively resolve properties assigned to this entity, directly or indirectly via
        folders.

        Parent property references are currently only being resolved for modelEntities.

        Parameters
        ----------
        model : `model.model`
            The DataM8 model to lookup up the property values. This normally is the same
            model as the one this EntityWrapper resides in, but could technically be a
            separate model.
        properties : `Sequence[PropertyReference]`
            PropertyReferences that should be looked up recursively.
        """
        if len(properties) == 0:
            return

        converted_properties = [PropertyReference.from_model_ref(pr) for pr in properties]

        logger.debug(
            "%s - %s",
            wrapper.locator,
            [f"{p.property}:{p.value}" for p in converted_properties],
        )

        for ref in converted_properties:
            property_value = self.propertyValues.get(f"{ref.property}/{ref.value}")
            wrapper._properties[property_value.locator] = property_value.entity

            # NOTE: break recursion
            if property_value.entity.properties:
                self._resolve_properties(wrapper, property_value.entity.properties)

    def get_entity_iterator(self) -> Iterator[EntityWrapperVariant]:
        for entity_type in b.EntityType:
            logger.log(5, f"Iterating... {entity_type}")

            for _, wrapper in self[entity_type.value].items():
                logger.log(5, f"Iterating... {str(wrapper.locator)}")
                yield wrapper  # type: ignore[ty:invalid-yield]

    def get_generator_target(self, name: str, /) -> s.GeneratorTarget:
        if name == opts.default_target:
            return self.get_generator_default_target()

        for target in self.solution.generatorTargets:
            if target.name == name:
                return target

        raise utils.create_error(errors.InvalidGeneratorTargetError(name))

    def get_generator_default_target(self) -> s.GeneratorTarget:
        default_targets = list(filter(lambda t: t.isDefault, self.solution.generatorTargets))

        match len(default_targets):
            case 0:
                raise Exception("No default target defined")
            case 1:
                return default_targets.pop()
            case _:
                raise Exception("Multiple default targets defined")

    def get_entity(
        self, name: str, /, entity_type: b.EntityType
    ) -> EntityWrapper[b.BaseEntityType]:
        locator = Locator.from_path(f"{entity_type.value}/{name}")
        entity = self[entity_type.value].get(locator)

        if not entity.resolved:
            self.resolve_wrapper(entity)

        return entity

    def get_zone_for_entity(
        self, wrapper: EntityWrapper[m.ModelEntity], /
    ) -> EntityWrapper[z.Zone]:
        if len(wrapper.locator.folders) == 0:
            raise utils.create_error(errors.InvalidLocatorError(str(wrapper.locator)))

        folder_name = wrapper.locator.folders[0]
        try:
            zone = self.zones.get_where(
                lambda w: w.entity.localFolderName == folder_name
                or w.entity.name == folder_name
            )
        except Exception as err:
            raise utils.create_error(f"No Zone found for '{wrapper.locator}'") from err

        return zone

    def get_data_module(self, name: str, /, data_product: str) -> dp.DataModule:
        """Get a data module for a data  product by name."""
        # TODO: split data module up from data product and fill `self.dataModules`
        for data_module in self.dataProducts[data_product].entity.dataModules:
            if data_module.name == name:
                return data_module

        raise errors.EntityNotFoundError(f"dataModule {data_product}:{name}")

    def has_locator(self, locator: Locator | str, /) -> bool:
        locator_ = _ensure_locator(locator)
        return locator_ in self[locator_.entityType]

    def __contains__(self, locator: LocatorOrString, /) -> bool:
        return self.has_locator(locator)

    def get_entity_by_locator(self, locator: str | Locator, /) -> EntityWrapperVariant:
        """
        Retrieve a single entity by its locator.

        This is implemented as a directly dictionary key lookup, and will fail if
        the entity / locator does not exist.

        Parameters
        ----------
        locator : `str` or `Locator`
            The locator of the entity to retrieve.

        Returns
        -------
        `EntityWrapper`
            Of an unknown entity type. Needs to be type hinted manually if required.
        """
        locator = _ensure_locator(locator)
        wrapper = self[locator.entityType].get(locator)

        if wrapper.is_deleted:
            raise utils.create_error(Exception("Entity has been deleted"))

        return wrapper  # type: ignore

    def get_base_path_for_entity_type(self, _type: b.EntityType, /) -> Path:
        match _type:
            case b.EntityType.MODEL_ENTITIES | b.EntityType.FOLDERS:
                base_file_path = config.solution_folder_path / self.solution.modelPath
            case _:
                base_file_path = config.solution_folder_path / self.solution.basePath

        return base_file_path

    def get_source_file_for_locator(self, locator: Locator, /) -> Path:
        _type = b.EntityType(locator.entityType)
        base_path = self.get_base_path_for_entity_type(_type)
        if locator.entityName is None:
            raise utils.create_error(errors.InvalidLocatorError(str(locator)))

        if _type == b.EntityType.FOLDERS:
            return base_path.joinpath(
                *locator.folders,
                locator.entityName,
                ".properties.json",
            )
        if _type == b.EntityType.MODEL_ENTITIES:
            return base_path.joinpath(*locator.folders, locator.entityName).with_suffix(".json")

        existing_files = sorted(
            (
                ref.file_path
                for ref in self._model_files.values()
                if ref._type == _type
            ),
            key=lambda path: len(path.as_posix()),
        )
        if existing_files:
            return existing_files[0]
        return base_path.joinpath(*locator.folders, _default_base_file_name_for_type(_type))

    @overload
    def add_entity(
        self, locator: Locator | str, /, content: dict[str, Any]
    ) -> EntityWrapper[b.BaseEntityType]: ...

    @overload
    def add_entity[T: b.BaseEntityType](
        self, locator: Locator | str, /, content: T
    ) -> EntityWrapper[T]: ...

    def add_entity[T: b.BaseEntityType](
        self, locator: Locator | str, /, content: dict[str, Any] | T
    ) -> EntityWrapper[T]:
        _locator = _ensure_locator(locator)
        _type = b.EntityType(_locator.entityType)

        assert _locator.entityName is not None, (
            "Only locators for entities should be provided to 'add_entity'"
        )
        source_file_path = self.get_source_file_for_locator(_locator)

        match content:
            case dict() as c:
                entity_content = dict(c)
                entity_content["name"] = _locator.entityName
                if _type == b.EntityType.MODEL_ENTITIES:
                    entity_content["id"] = self.get_next_model_id()
                if _type == b.EntityType.FOLDERS:
                    entity_content["path"] = "/".join([*_locator.folders, _locator.entityName])
                new_entity = class_from_type(_type).from_dict(entity_content)
            case m.ModelEntity() as me:
                new_entity = me
                new_entity.id = self.get_next_model_id()
                new_entity.name = _locator.entityName
            case _ as rest:
                new_entity = rest

        try:
            new_wrapper = EntityWrapper(
                locator=_locator,
                source_file=source_file_path,
                entity=new_entity,
            )
            new_wrapper._changed = True
            self.resolve_wrapper(new_wrapper)
        except ValidationError as err:
            raise utils.create_error(err)

        typed_wrapper = cast(EntityWrapper[T], new_wrapper)
        cast(EntityRepository[T], self[_type.value]).add(_locator, typed_wrapper)
        self.update_file_reference(
            _type=_type, file_path=source_file_path, locators=[new_wrapper.locator]
        )

        return typed_wrapper

    def clone_entity(
        self,
        locator: Locator | str,
        /,
        new_locator: Locator | str,
    ) -> EntityWrapper[b.BaseEntityType]:
        to_clone = _ensure_locator(locator)
        new_locator = _ensure_locator(new_locator)

        if to_clone.entityType != new_locator.entityType:
            raise utils.create_error(
                Exception(
                    "The entity type of both locators need to be the same when cloning an entity"
                )
            )

        cloned_entity: dict[str, Any] = (
            self.get_entity_by_locator(to_clone).entity.model_copy().model_dump()
        )
        new_wrapper = self.add_entity(new_locator, cloned_entity)

        return new_wrapper

    def rename_entity(
        self,
        _from: Locator | str,
        /,
        _to: Locator | str,
        content: dict[str, Any] | None = None,
    ) -> EntityWrapperVariant:
        from_locator = _ensure_locator(_from)
        to_locator = _ensure_locator(_to)

        if from_locator == to_locator:
            wrapper = self.get_entity_by_locator(from_locator)
            if content:
                wrapper.update(**content)
            return wrapper

        if from_locator.entityType != to_locator.entityType:
            raise utils.create_error(
                ValueError("Source and target must use the same entity type")
            )

        entity_type = b.EntityType(from_locator.entityType)
        if entity_type in {b.EntityType.MODEL_ENTITIES, b.EntityType.FOLDERS}:
            raise utils.create_error(
                ValueError("Use /entities/move for model entity and folder renames")
            )

        if from_locator.entityName is None or to_locator.entityName is None:
            raise utils.create_error(
                errors.InvalidLocatorError(f"{from_locator} -> {to_locator}")
            )

        if self.has_locator(to_locator):
            raise utils.create_error(
                ValueError(f"Target of entity rename already exists: {to_locator}")
            )

        if entity_type == b.EntityType.PROPERTY_VALUES:
            if len(to_locator.folders) != 1:
                raise utils.create_error(errors.InvalidLocatorError(str(to_locator)))
        elif to_locator.folders:
            raise utils.create_error(errors.InvalidLocatorError(str(to_locator)))

        repository = self[from_locator.entityType]
        wrapper = cast(
            EntityWrapper[b.BaseEntityType],
            self.get_entity_by_locator(from_locator),
        )
        source_file = wrapper.source_file

        del repository[from_locator]
        wrapper.reset(to_locator, source_file=source_file)

        patch = dict(content or {})
        patch["name"] = to_locator.entityName
        if entity_type == b.EntityType.PROPERTY_VALUES:
            patch["property"] = to_locator.folders[0]
        wrapper.update(**patch)
        self.resolve_wrapper(wrapper)
        wrapper._changed = True
        repository[to_locator] = wrapper

        file_ref = self._model_files.get(source_file)
        if file_ref is not None:
            file_ref.renamed_locators[from_locator] = to_locator
            file_ref.locators = [
                to_locator if locator == from_locator else locator
                for locator in file_ref.locators
            ]
            if to_locator not in file_ref.locators:
                file_ref.locators.append(to_locator)

        logger.debug("Renamed %s to %s", from_locator, to_locator)
        return cast(EntityWrapperVariant, wrapper)

    @staticmethod
    def _get_subtree_root_locator(locator: Locator) -> Locator:
        if locator.entityName is None:
            return locator
        return Locator(
            entityType=locator.entityType,
            folders=[*locator.folders, locator.entityName],
            entityName=None,
        )

    def get_entities_for_locator(
        self,
        locator: Locator | str,
        /,
    ) -> list[EntityWrapperVariant]:
        search_locator = _ensure_locator(locator)
        entities: list[EntityWrapperVariant] = []
        seen_locators: set[Locator] = set()

        def add(wrapper: EntityWrapperVariant) -> None:
            if wrapper.locator not in seen_locators:
                entities.append(wrapper)
                seen_locators.add(wrapper.locator)

        if self.has_locator(search_locator):
            add(self.get_entity_by_locator(search_locator))

        if search_locator.entityType == b.EntityType.FOLDERS.value:
            folder_root = self._get_subtree_root_locator(search_locator)
            model_root = Locator(
                entityType=b.EntityType.MODEL_ENTITIES.value,
                folders=folder_root.folders,
                entityName=None,
            )
            for wrapper in self.get_entity_iterator():
                if (
                    wrapper.locator.entityType == b.EntityType.FOLDERS.value
                    and wrapper.locator in folder_root
                ) or (
                    wrapper.locator.entityType == b.EntityType.MODEL_ENTITIES.value
                    and wrapper.locator in model_root
                ):
                    add(wrapper)
            return entities

        if search_locator.entityName is None:
            for wrapper in self.get_entities(search_locator):
                add(wrapper)

        return entities

    @staticmethod
    def _get_rebased_locator(
        current: Locator,
        *,
        from_root: Locator,
        to_root: Locator,
    ) -> Locator:
        def parts(locator: Locator) -> list[str]:
            return [*locator.folders, *([locator.entityName] if locator.entityName else [])]

        from_parts = parts(from_root)
        current_parts = parts(current)
        if current_parts[: len(from_parts)] != from_parts:
            raise utils.create_error(
                ValueError(f"{current} is outside move root {from_root}")
            )

        rebased_parts = [*parts(to_root), *current_parts[len(from_parts) :]]
        if current.entityName is None:
            return Locator(
                entityType=current.entityType,
                folders=rebased_parts,
                entityName=None,
            )
        if not rebased_parts:
            raise utils.create_error(ValueError("Cannot move entity to an empty locator"))
        return Locator(
            entityType=current.entityType,
            folders=rebased_parts[:-1],
            entityName=rebased_parts[-1],
        )

    def delete_entities(self, locator: Locator | str, /) -> list[Locator]:
        wrappers = self.get_entities_for_locator(locator)
        if not wrappers:
            raise utils.create_error(errors.InvalidLocatorError(str(locator)))

        for wrapper in wrappers:
            wrapper._deleted = True
        return [wrapper.locator for wrapper in wrappers]

    def delete_entity(self, locator: Locator, /) -> None:
        if locator.entityName is None:
            raise utils.create_error("When deleting an entity, the locator must point to an entity")

        self.delete_entities(locator)

    def move_entities(
        self, _from: Locator | str, /, _to: Locator | str
    ) -> list[EntityWrapperVariant]:
        from_locator = _ensure_locator(_from)
        to_locator = _ensure_locator(_to)

        if from_locator == to_locator:
            return []

        wrappers = self.get_entities_for_locator(from_locator)
        if not wrappers:
            raise utils.create_error(errors.InvalidLocatorError(str(_from)))

        move_plan: list[tuple[EntityWrapperVariant, Locator]] = []
        if from_locator.entityType == b.EntityType.FOLDERS.value:
            folder_from_root = self._get_subtree_root_locator(from_locator)
            folder_to_root = self._get_subtree_root_locator(to_locator)
            model_from_root = Locator(
                entityType=b.EntityType.MODEL_ENTITIES.value,
                folders=folder_from_root.folders,
                entityName=None,
            )
            model_to_root = Locator(
                entityType=b.EntityType.MODEL_ENTITIES.value,
                folders=folder_to_root.folders,
                entityName=None,
            )
            for wrapper in wrappers:
                if wrapper.locator.entityType == b.EntityType.FOLDERS.value:
                    target = self._get_rebased_locator(
                        wrapper.locator,
                        from_root=folder_from_root,
                        to_root=folder_to_root,
                    )
                else:
                    target = self._get_rebased_locator(
                        wrapper.locator,
                        from_root=model_from_root,
                        to_root=model_to_root,
                    )
                move_plan.append((wrapper, target))
        else:
            from_root = self._get_subtree_root_locator(from_locator)
            to_root = self._get_subtree_root_locator(to_locator)
            move_plan = [
                (
                    wrapper,
                    self._get_rebased_locator(
                        wrapper.locator,
                        from_root=from_root,
                        to_root=to_root,
                    ),
                )
                for wrapper in wrappers
            ]

        source_locators = {wrapper.locator for wrapper, _ in move_plan}
        target_locators = [target for _, target in move_plan]
        if len(set(target_locators)) != len(target_locators):
            raise utils.create_error(ValueError("Move produces duplicate target locators"))
        for target in target_locators:
            if self.has_locator(target) and target not in source_locators:
                raise utils.create_error(
                    ValueError(f"Target of entity move already exists: {target}")
                )

        prepared: list[tuple[EntityWrapperVariant, EntityWrapperVariant]] = []
        for wrapper, target in move_plan:
            clone = wrapper.model_copy(deep=True)
            clone.reset(target, source_file=self.get_source_file_for_locator(target))
            clone.entity.name = target.entityName or clone.entity.name
            if isinstance(clone.entity, f.Folder):
                clone.entity.path = "/".join([*target.folders, target.entityName or ""])
            self.resolve_wrapper(clone)  # pyright: ignore[reportArgumentType]
            clone._changed = True
            prepared.append((wrapper, clone))

        new_wrappers: list[EntityWrapperVariant] = []
        for source_wrapper, target_wrapper in prepared:
            source_wrapper._deleted = True
            repository = self[target_wrapper.locator.entityType]
            repository[target_wrapper.locator] = target_wrapper  # type: ignore
            self.update_file_reference(
                _type=b.EntityType(target_wrapper.locator.entityType),
                file_path=target_wrapper.source_file,
                locators=[target_wrapper.locator],
            )
            new_wrappers.append(target_wrapper)

        logger.debug("%s entities have been moved to %s", len(new_wrappers), str(to_locator))

        return new_wrappers

    def move_entity(
        self, _from: Locator, /, _to: Locator, *, force: bool = False
    ) -> EntityWrapperVariant:
        if _from.entityName is None:
            raise utils.create_error(
                Exception(
                    "When moving an entity a locator pointing to a single entity must be used"
                )
            )

        new_locator = _to.clone()
        new_locator.entityType = _from.entityType
        new_locator.entityName = _to.entityName or _from.entityName

        if self.has_locator(new_locator) and not force:
            raise utils.create_error(
                Exception(f"Target of entity move does already exist: {new_locator}")
            )

        from_wrapper = self.get_entity_by_locator(_from)
        _type = b.EntityType(_from.entityType)
        new_source_file = self.get_source_file_for_locator(new_locator)
        to_wrapper = from_wrapper.model_copy(deep=True)
        to_wrapper.reset(new_locator, source_file=new_source_file)
        to_wrapper.entity.name = new_locator.entityName
        if isinstance(to_wrapper.entity, f.Folder):
            to_wrapper.entity.path = "/".join(
                [*new_locator.folders, new_locator.entityName]
            )
        self.resolve_wrapper(to_wrapper)  # pyright: ignore[reportArgumentType]
        to_wrapper._changed = True

        from_wrapper._deleted = True
        # type checks are incorrect due to invariance in generic types
        self[_from.entityType][new_locator] = to_wrapper  # type: ignore

        self.update_file_reference(
            _type=_type, file_path=new_source_file, locators=[to_wrapper.locator]
        )

        logger.debug(f"Moved {_from} to {new_locator}")

        return to_wrapper

    def get_entities_by_property(
        self,
        property_locator: str | Locator,
        /,
        model_locator: str | Locator = "modelEntities/",
    ) -> list[EntityWrapperVariant]:
        locator = _ensure_locator(property_locator)
        if locator.entityName is None or locator.entityType not in [
            b.EntityType.PROPERTIES.value,
            b.EntityType.PROPERTY_VALUES.value,
        ]:
            raise utils.create_error(errors.InvalidLocatorError(str(locator)))

        property_value = self.propertyValues.get(locator)

        results = [
            wrapper
            for wrapper in self.get_entities(model_locator)
            if property_value.locator in wrapper.properties
        ]

        return results

    def get_entity_by_selector(
        self, selector: str, /, *, by: opts.Selectors
    ) -> EntityWrapperVariant:
        match by:
            case opts.Selectors.NAME:
                for wrapper in self.modelEntities.values():
                    if wrapper.entity.name == selector:
                        return wrapper
                raise errors.EntityNotFoundError(selector)
            case opts.Selectors.ID:
                try:
                    id = int(selector)
                except ValueError as err:
                    raise utils.create_error(
                        ValueError(f"Model ID '{selector}' is not a valid number")
                    ) from err
                return self.modelEntities.get_by_id(id)
            case opts.Selectors.LOCATOR:
                return self.get_entity_by_locator(selector)
            case _:
                raise NotImplementedError(f"by {by}")

    def get_all_entities(self) -> list[EntityWrapperVariant]:
        return [wrapper for wrapper in self.get_entity_iterator()]

    def get_entities(self, search_locator: str | Locator, /) -> list[EntityWrapperVariant]:
        """
        Retrieve a list of EntityWrappers that are hierarchically underneath the
        given locator.

        Parameters
        ----------
        search_locator : `str` or `Locator`
            The parent locator to search for entities.

        Returns
        -------
        `list[EntityWrapper]`
            Since the entityType is not known beforehand type hints for the
            entities are not available automatically and need to be added manually.
        """
        search_locator = _ensure_locator(search_locator)

        if search_locator == ROOT_LOCATOR:
            return self.get_all_entities()

        child_locators = self.get_child_locators(search_locator)

        if len(child_locators) == 0:
            return []

        entity_repository = self[search_locator.entityType]
        entities = [
            entity_repository[_loc]
            if entity_repository[_loc].resolved
            else self.resolve_wrapper(entity_repository[_loc])
            for _loc in child_locators
        ]

        return entities  # type: ignore

    def get_child_locators(self, search_locator: str | Locator, /) -> list[Locator]:
        """
        Retrieve all enties located underneath the given locator, works for all
        items not only model entities.

        Only locators to actual entities are return, no "intermediate" locators point to folders.

        Parameters
        ----------
        search_locator : `str` or `Locator`
            The locator used for searching. It itself is not included in the results.

        Returns
        -------
        `list[Locator]`
            Since the entityType is not known beforehand type hints for the
            entities are not available automatically and need to be added manually.
        """
        search_locator = _ensure_locator(search_locator)
        found_wrappers = self[search_locator.entityType].get_many(search_locator)
        found_locators = [wrapper.locator for wrapper in found_wrappers]

        return found_locators

    def save(self, locator: str | None = None, /) -> None:
        """
        Saves the current state of the model or a specific entity to the corresponding json file.
        """
        changed_wrappers = [w for w in self.get_entities(locator or "/") if w.has_changed]
        deleted_wrappers = [w for w in self.get_entities(locator or "/") if w.is_deleted]

        no_of_changes = len(changed_wrappers)
        no_of_deletions = len(deleted_wrappers)

        if no_of_changes == 0 and no_of_deletions == 0:
            logger.info("Nothing has changed")
            return

        # group change entities by file to minimize disk operations
        file_to_wrappers: dict[Path, dict[str, list[EntityWrapperVariant]]] = {}

        for _p, file_ref in self._model_files.items():
            to_be_saved = {
                "changed": [w for w in changed_wrappers if w.locator in file_ref.locators],
                "deleted": [w for w in deleted_wrappers if w.locator in file_ref.locators],
            }
            if len(to_be_saved["deleted"]) == 0 and len(to_be_saved["changed"]) == 0:
                continue

            file_to_wrappers[_p] = to_be_saved

        logger.info(
            "Saving %s changed files, with %s changed entities and %s deleted entities",
            len(file_to_wrappers.keys()),
            no_of_changes,
            no_of_deletions,
        )

        for _file in file_to_wrappers:
            logger.debug(f"Saving to {_file}")

            if _file.exists():
                self._model_files[_file].update(wrappers=file_to_wrappers[_file]["changed"])
                self._model_files[_file].delete(wrappers=file_to_wrappers[_file]["deleted"])
            else:
                self._model_files[_file].create(wrappers=file_to_wrappers[_file]["changed"])

            # reset _changed attribute for saved entities
            for wrapper in file_to_wrappers[_file]["changed"]:
                wrapper._changed = False

            for wrapper in file_to_wrappers[_file]["deleted"]:
                del self[wrapper.locator.entityType][wrapper.locator]

        # remove file refs if there are no more locators associated with them

        self.cleanup_entity_file_references()
        self.cleanup_deleted_model_entity_directories(deleted_wrappers)

        for wrapper in deleted_wrappers:
            if (
                wrapper.locator.entityType == b.EntityType.FOLDERS.value
                and wrapper.locator.entityName
            ):
                self.cleanup_directories(
                    config.solution_folder_path
                    / self.solution.basePath
                    / Path(*wrapper.locator.folders, wrapper.locator.entityName),
                    config.solution_folder_path
                    / self.solution.modelPath
                    / Path(*wrapper.locator.folders, wrapper.locator.entityName),
                )

    def cleanup_deleted_model_entity_directories(
        self,
        deleted_wrappers: list[EntityWrapperVariant],
    ) -> None:
        model_root = self.get_base_path_for_entity_type(b.EntityType.MODEL_ENTITIES)
        for wrapper in deleted_wrappers:
            locator = wrapper.locator
            if (
                locator.entityType != b.EntityType.MODEL_ENTITIES.value
                or locator.entityName is None
            ):
                continue
            function_directory = model_root.joinpath(
                *locator.folders,
                locator.entityName,
            )
            if function_directory.is_dir():
                if function_directory.is_symlink() or function_directory.is_junction():
                    function_directory.unlink()
                else:
                    shutil.rmtree(function_directory)

    def cleanup_entity_file_references(self) -> None:
        deleted_files: list[Path] = []

        for file_ref in self._model_files:
            if len(self._model_files[file_ref].locators) == 0:
                deleted_files.append(file_ref)

        for _file in deleted_files:
            del self._model_files[_file]

    def cleanup_directories(self, *start_paths: Path) -> None:
        for start_path in start_paths:
            if not start_path.is_dir():
                continue
            for directory, _, _ in start_path.walk(top_down=False):
                if directory.exists() and not any(directory.iterdir()):
                    utils.delete_path(directory)

    def get_unsaved_entities(self) -> tuple[list[Locator], list[Locator]]:
        """Returns a list of changed and delete locators"""
        changed = [wrapper.locator for wrapper in self.get_entity_iterator() if wrapper.has_changed]
        deleted = [wrapper.locator for wrapper in self.get_entity_iterator() if wrapper.is_deleted]
        return changed, deleted


class EntityFileRef:
    def __init__(
        self, /, _type: b.EntityType, file_path: Path, locators: list[Locator] | None = None
    ) -> None:
        self._type: b.EntityType = _type
        self.file_path: Path = file_path
        self.locators: list[Locator] = locators or []
        self.renamed_locators: dict[Locator, Locator] = {}

    def __repr__(self) -> str:
        return f"EntityFileRef({self._type} file={self.file_path})"

    def create(self, *, wrappers: list[EntityWrapperVariant]) -> None:
        logger.debug(f"Trying to create {self.file_path} with %s entities ", len(wrappers))

        if len(wrappers) == 0:
            return

        entities = [wrapper.entity for wrapper in wrappers]
        _model = None

        match self._type:
            case b.EntityType.MODEL_ENTITIES:
                # model entities are special, since those files only contain a single entry
                if len(entities) != 1:
                    raise utils.create_error(
                        Exception(
                            "Only one wrapper to update allowed when updating single model file"
                        )
                    )
                _model = entities[0]
            case b.EntityType.FOLDERS:
                _class = b.Folders
            case b.EntityType.PROPERTIES:
                _class = b.Properties
            case b.EntityType.PROPERTY_VALUES:
                _class = b.PropertyValues
            case b.EntityType.ZONES:
                _class = b.Zones
            case b.EntityType.DATA_TYPES:
                _class = b.DataTypes
            case b.EntityType.DATA_SOURCE_TYPES:
                _class = b.DataSourceTypes
            case b.EntityType.DATA_PRODUCTS:
                _class = b.DataProducts
            case b.EntityType.DATA_MODULES:
                _class = b.DataModules
            case b.EntityType.ATTRIBUTE_TYPES:
                _class = b.AttributeTypes
            case b.EntityType.DATA_SOURCES:
                _class = b.DataSources
            case _:
                raise utils.create_error(NotImplementedError(self._type.value))

        # one of both is always defined
        _model = _model or _class.from_dict(  # pyright: ignore [reportPossiblyUnboundVariable]
            {"type": self._type.value, self._type.value: entities},
        )

        utils.mkdir(self.file_path.parent, recursive=True)
        _model.to_json_file(self.file_path, "x", MODEL_DUMP_OPTIONS)

    def delete(self, *, wrappers: list[EntityWrapperVariant]) -> bool:
        """
        Raises
        ------
        FileNotFoundError
            If the file to be updated does not exist
        """
        if len(wrappers) == 0:
            return False

        logger.debug(f"Trying to delete %s entities from {self.file_path}", len(wrappers))

        match self._type:
            case b.EntityType.MODEL_ENTITIES:
                if len(wrappers) > 1:
                    raise utils.create_error(
                        "Only one wrapper to update allowed when updating single model file"
                    )
                utils.delete_path(self.file_path)
                self.locators = []
                return True

            case _:
                current_content = b.BaseEntities.from_json_file(self.file_path)
                entities: list[b.BaseEntityType] = getattr(current_content.root, self._type.value)
                if self._type == b.EntityType.PROPERTY_VALUES:
                    deleted_keys = {
                        (getattr(wrapper.entity, "property", None), wrapper.entity.name)
                        for wrapper in wrappers
                    }
                    entities = [
                        entity
                        for entity in entities
                        if (getattr(entity, "property", None), entity.name)
                        not in deleted_keys
                    ]
                else:
                    deleted_names = {wrapper.entity.name for wrapper in wrappers}
                    entities = [
                        entity for entity in entities if entity.name not in deleted_names
                    ]

                setattr(current_content.root, self._type.value, entities)

                with open(self.file_path, "w") as _file:
                    _file.write(current_content.model_dump_json(**MODEL_DUMP_OPTIONS))

                self.locators = [
                    loc for loc in self.locators if loc not in [w.locator for w in wrappers]
                ]

                # NOTE: this should actually never not be case, if not the something went majorly wrong
                assert len(self.locators) == len(entities)

                if len(self.locators) == 0:
                    utils.delete_path(self.file_path)
                    return True

                return False

    def update(self, *, wrappers: list[EntityWrapperVariant]) -> None:
        """
        Raises
        ------
        FileNotFoundError
            If the file to be updated does not exist
        """
        if len(wrappers) == 0:
            return

        logger.debug(f"Trying to update {self.file_path} with %s entities", len(wrappers))

        match self._type:
            case b.EntityType.MODEL_ENTITIES:
                if len(wrappers) > 1:
                    raise utils.create_error(
                        "Only one wrapper to update allowed when updating single model file"
                    )
                current_content = wrappers[0].entity
            case _:
                current_content = b.BaseEntities.from_json_file(self.file_path)
                entities: list[b.BaseEntityType] = getattr(current_content.root, self._type.value)

                for wrapper in wrappers:
                    previous_locator = next(
                        (
                            old_locator
                            for old_locator, new_locator in self.renamed_locators.items()
                            if new_locator == wrapper.locator
                        ),
                        None,
                    )
                    replaced = False
                    for index, existing_entity in enumerate(entities):
                        if previous_locator is not None:
                            same_name = existing_entity.name == previous_locator.entityName
                            same_property = (
                                self._type != b.EntityType.PROPERTY_VALUES
                                or getattr(existing_entity, "property", None)
                                == (
                                    previous_locator.folders[0]
                                    if previous_locator.folders
                                    else None
                                )
                            )
                            matches = same_name and same_property
                        elif self._type == b.EntityType.PROPERTY_VALUES:
                            matches = (
                                existing_entity.name == wrapper.entity.name
                                and getattr(existing_entity, "property", None)
                                == getattr(wrapper.entity, "property", None)
                            )
                        else:
                            matches = existing_entity.name == wrapper.entity.name

                        if matches:
                            entities[index] = wrapper.entity
                            replaced = True
                            break

                    if not replaced:
                        entities.append(wrapper.entity)
                    if previous_locator is not None:
                        self.renamed_locators.pop(previous_locator, None)

                setattr(current_content.root, self._type.value, entities)

        current_content.to_json_file(self.file_path, "w", MODEL_DUMP_OPTIONS)

        logger.info("Saved %s entities to %s", len(wrappers), self.file_path)
