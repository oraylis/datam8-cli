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

from datetime import UTC, datetime
from typing import Any, Literal

from deepdiff import DeepDiff
from deepdiff.helper import CannotCompare
from deepdiff.model import DiffLevel

from datam8.model import entity_wrapper as ew
from datam8.model import locator as l
from datam8_model import attribute as at
from datam8_model import data_type as dt
from datam8_model import model as m
from datam8_model import property as p

from . import factory, model, utils


class _SourceDefinitionsUnset:
    pass


_SOURCE_DEFINITIONS_UNSET = _SourceDefinitionsUnset()


def _property_references(value: Any, property_name: str, /) -> list[p.PropertyReference] | None:
    if value is None or value == []:
        return None
    if not isinstance(value, list):
        raise utils.create_error(ValueError(f"{property_name} must be a list"))
    return [p.PropertyReference.model_validate(item) for item in value]


def _sources_from_definitions(
    definitions: list[dict[str, Any]], data_source: str, /, *, metadata_location: str | None = None
) -> list[m.ExternalModelSource]:
    grouped: dict[
        tuple[str, str | None, str | None],
        tuple[list[m.SourceAttributeMapping], list[p.PropertyReference] | None],
    ] = {}
    seen_mappings: set[tuple[str, str | None, str | None, str, str]] = set()

    for row in definitions:
        if not isinstance(row, dict):
            raise utils.create_error(ValueError("Each source definition must be a dictionary"))
        location = row.get("sourceLocation")
        source_name = row.get("sourceName")
        target_name = row.get("targetName")
        alias = row.get("sourceAlias")
        row_metadata_location = row.get("metadataLocation", metadata_location)
        if (
            not isinstance(location, str)
            or not location
            or not isinstance(source_name, str)
            or not source_name
            or not isinstance(target_name, str)
            or not target_name
        ):
            raise utils.create_error(
                ValueError("sourceLocation, sourceName and targetName must be non-empty strings")
            )
        if alias is not None and not isinstance(alias, str):
            raise utils.create_error(ValueError("sourceAlias must be a string or null"))
        if row_metadata_location is not None and (
            not isinstance(row_metadata_location, str) or not row_metadata_location
        ):
            raise utils.create_error(
                ValueError("metadataLocation must be a non-empty string or null")
            )

        key = (location, alias, row_metadata_location)
        mapping_key = (location, alias, row_metadata_location, source_name, target_name)
        if mapping_key in seen_mappings:
            raise utils.create_error(ValueError(f"Duplicate source mapping: {mapping_key}"))
        seen_mappings.add(mapping_key)

        source_properties = _property_references(row.get("sourceProperties"), "sourceProperties")
        mapping_properties = _property_references(row.get("mappingProperties"), "mappingProperties")
        source_data_type = row.get("sourceDataType")
        if source_data_type is not None:
            source_data_type = dt.DataType.model_validate(source_data_type)
        if key in grouped:
            mappings, existing_properties = grouped[key]
            if (
                existing_properties is not None
                and source_properties is not None
                and existing_properties != source_properties
            ):
                raise utils.create_error(
                    ValueError(f"Conflicting sourceProperties for source: {key}")
                )
            if source_properties is not None:
                existing_properties = source_properties
            mappings.append(
                m.SourceAttributeMapping(
                    sourceName=source_name,
                    targetName=target_name,
                    sourceDataType=source_data_type,
                    properties=mapping_properties,
                )
            )
            grouped[key] = (mappings, existing_properties)
        else:
            grouped[key] = (
                [
                    m.SourceAttributeMapping(
                        sourceName=source_name,
                        targetName=target_name,
                        sourceDataType=source_data_type,
                        properties=mapping_properties,
                    )
                ],
                source_properties,
            )

    return [
        m.ExternalModelSource(
            dataSource=data_source,
            sourceLocation=location,
            metadataLocation=row_metadata_location,
            sourceAlias=alias,
            properties=properties,
            mapping=mappings,
        )
        for (location, alias, row_metadata_location), (mappings, properties) in grouped.items()
    ]


def _default_source(
    data_source: str,
    source_location: str,
    mappings: list[m.SourceAttributeMapping],
    *,
    existing_source: m.ExternalModelSource | None = None,
    metadata_location: str | None = None,
) -> list[m.ExternalModelSource]:
    if existing_source is not None:
        existing_mappings = {
            (mapping.sourceName, mapping.targetName): mapping
            for mapping in existing_source.mapping or []
        }
        for mapping in mappings:
            existing = existing_mappings.get((mapping.sourceName, mapping.targetName))
            if existing is not None:
                by_name = {prop.property: prop for prop in existing.properties or []}
                by_name.update({prop.property: prop for prop in mapping.properties or []})
                mapping.properties = list(by_name.values()) or existing.properties
    return [
        m.ExternalModelSource(
            sourceLocation=source_location,
            dataSource=data_source,
            metadataLocation=metadata_location,
            sourceAlias=existing_source.sourceAlias if existing_source is not None else None,
            properties=existing_source.properties if existing_source is not None else None,
            mapping=mappings,
        )
    ]


def compare_entity_with_source(
    locator: l.LocatorOrString,
    /,
    *,
    model: model.Model | None = None,
    mode: Literal["complete", "sources-only"] = "complete",
) -> tuple[ew.EntityWrapper[m.ModelEntity], DeepDiff]:
    """
    Compares a model entity with its current source representation.

    Parameters
    --------------
    locator : `Locator | str`
        The locator of the model entity to refresh.

    Returns
    -------
    :class:EntityWrapper[ModelEntity]
        A copy of the original wrapper with updated values and _changed set to True
    """
    model_ = model or factory.get_model()
    wrapper = model_.modelEntities[locator].model_copy(deep=True)
    original_entity = wrapper.entity.model_copy(deep=True)

    current_attributes = [attr.model_copy(deep=True) for attr in wrapper.entity.attributes]
    current_by_name = {attr.name: attr for attr in current_attributes}
    previously_mapped_targets = {
        mapping.targetName
        for source in wrapper.entity.sources
        if isinstance(source, m.ExternalModelSource)
        for mapping in source.mapping or []
    }
    groups: list[tuple[m.ExternalModelSource, str, int]] = []
    seen_locations: set[tuple[str, str]] = set()
    group_indices: dict[tuple[str, str], list[int]] = {}
    for index, existing in enumerate(wrapper.entity.sources):
        if not isinstance(existing, m.ExternalModelSource):
            continue
        location = existing.metadataLocation or existing.sourceLocation
        if existing.metadataLocation is not None:
            key = (existing.dataSource, location)
            if key in seen_locations:
                group_indices[key].append(index)
                continue
            seen_locations.add(key)
            group_indices[key] = [index]
        groups.append((existing, location, index))

    refreshed_groups: dict[tuple[str, str], list[m.ExternalModelSource]] = {}
    refreshed_by_index: dict[int, list[m.ExternalModelSource]] = {}
    described_attributes: dict[str, at.Attribute] = {}
    described_properties: dict[str, p.PropertyReference] = {}
    for existing, location, index in groups:
        if mode == "sources-only":
            refreshed = read_external_sources(
                existing.dataSource,
                location,
                model=model_,
                current_source=existing,
                metadata_location=existing.metadataLocation,
            )
        else:
            described = read_from_data_source(
                existing.dataSource,
                location,
                model=model_,
                existing_source=existing,
                metadata_location=existing.metadataLocation,
            )
            refreshed = [
                item for item in described.sources if isinstance(item, m.ExternalModelSource)
            ]
            for attr in described.attributes:
                previous = described_attributes.get(attr.name)
                comparable = {"ordinalNumber", "dateAdded", "dateModified"}
                if previous is not None and previous.model_dump(
                    mode="json", exclude=comparable
                ) != attr.model_dump(mode="json", exclude=comparable):
                    raise utils.create_error(ValueError(f"Conflicting attribute: {attr.name}"))
                described_attributes[attr.name] = attr
            for prop in described.properties or []:
                previous = described_properties.get(prop.property)
                if previous is not None and previous != prop:
                    raise utils.create_error(
                        ValueError(f"Conflicting entity property: {prop.property}")
                    )
                described_properties[prop.property] = prop

        if existing.metadataLocation is None:
            refreshed_by_index[index] = refreshed
        else:
            refreshed_groups[(existing.dataSource, location)] = refreshed

    for key, refreshed in refreshed_groups.items():
        indices = group_indices[key]
        for index in indices:
            refreshed_by_index[index] = []
        for index, source in zip(indices, refreshed):
            refreshed_by_index[index] = [source]
        if len(refreshed) > len(indices):
            refreshed_by_index[indices[-1]].extend(refreshed[len(indices) :])

    refreshed_sources: list[m.ExternalModelSource | m.InternalModelSource] = []
    for index, existing in enumerate(wrapper.entity.sources):
        if isinstance(existing, m.InternalModelSource):
            refreshed_sources.append(existing)
        else:
            refreshed_sources.extend(refreshed_by_index[index])
    wrapper.entity.sources = refreshed_sources

    if mode == "sources-only":
        wrapper._changed = wrapper.entity.sources != original_entity.sources
        return wrapper, DeepDiff(
            original_entity.model_dump(mode="json", exclude_none=True),
            wrapper.entity.model_dump(mode="json", exclude_none=True),
            threshold_to_diff_deeper=0,
        )

    if described_properties:
        entity_properties = {prop.property: prop for prop in wrapper.entity.properties or []}
        entity_properties.update(described_properties)
        wrapper.entity.properties = list(entity_properties.values()) or None
    for name, refreshed in described_attributes.items():
        old = current_by_name.get(name)
        if old is None:
            current_attributes.append(refreshed.model_copy(deep=True))
            continue
        refreshed = refreshed.model_copy(deep=True)
        # Connector metadata does not own locally modeled transformation settings.
        for field in (
            "displayName",
            "history",
            "expression",
            "expressionLanguage",
            "unit",
            "refactorNames",
            "dateDeleted",
        ):
            setattr(refreshed, field, getattr(old, field))
        if refreshed.dataType.type == old.dataType.type:
            refreshed.attributeType = old.attributeType
        properties = {prop.property: prop for prop in old.properties or []}
        properties.update({prop.property: prop for prop in refreshed.properties or []})
        refreshed.properties = list(properties.values()) or old.properties
        refreshed.dateAdded = old.dateAdded
        comparable = {"ordinalNumber", "dateAdded", "dateModified"}
        refreshed.dateModified = (
            datetime.now(UTC)
            if refreshed.model_dump(mode="json", exclude=comparable)
            != old.model_dump(mode="json", exclude=comparable)
            else old.dateModified
        )
        current_attributes[current_attributes.index(old)] = refreshed
    # cleanup attribute list (remove non-referenced attributes and update ordinal number)
    refreshed_targets = {
        mapping.targetName for source in wrapper.entity.sources for mapping in source.mapping or []
    }
    current_attributes = [
        attr
        for attr in current_attributes
        if attr.name not in previously_mapped_targets or attr.name in refreshed_targets
    ]

    # update ordinal numbers to account for new fields
    for idx, attr in enumerate(current_attributes, start=1):
        attr.ordinalNumber = idx

    wrapper.entity.attributes = current_attributes

    # defines how the deepdiff identifies the objects to compare when comparing lists
    # otherwise it just uses the list index which is not a good indicator
    # this function only covers source related parts of the model, anything else, e.g.
    # transformations are not driven by the source metadata, but modeled in DataM8 itself
    def compare_iterable(left: Any, right: Any, level: DiffLevel | None = None):
        if type(left) is not dict or type(right) is not dict:
            raise CannotCompare() from None

        # order of cases should be from leaf objects upwards
        match [left, right]:
            case [{"property": prop_l, "value": val_l}, {"property": prop_r, "value": val_r}]:
                return prop_l == prop_r and val_l == val_r
            case [{"targetName": trg_l, "sourceName": _}, {"targetName": trg_r, "sourceName": _}]:
                return trg_l == trg_r
            case [{"name": name_l, "ordinalNumber": _}, {"name": name_r, "ordinalNumber": _}]:
                return name_l == name_r
            case [
                {"dataSource": src_l, "sourceLocation": loc_l},
                {"dataSource": src_r, "sourceLocation": loc_r},
            ]:
                return src_l == src_r and loc_l == loc_r

        raise CannotCompare() from None

    diff_exclude = {"attributes": {"__all__": {"dateModified"}}}
    diff = DeepDiff(
        original_entity.model_dump(mode="json", exclude_none=True, exclude=diff_exclude),
        wrapper.entity.model_dump(mode="json", exclude_none=True, exclude=diff_exclude),
        iterable_compare_func=compare_iterable,
        threshold_to_diff_deeper=0,
    )

    wrapper._changed = diff != {}

    return wrapper, diff


def import_from_source(
    data_source: str,
    source_location: str,
    locator: l.LocatorOrString,
    /,
    *,
    model: model.Model | None = None,
) -> ew.EntityWrapper[m.ModelEntity]:
    model = model or factory.get_model()
    locator_ = l._ensure_locator(locator)

    new_entity = read_from_data_source(data_source, source_location, model=model)
    added_wrapper = model.add_entity(locator_, content=new_entity)

    return added_wrapper


def read_from_data_source(
    data_source: str,
    source_location: str,
    /,
    *,
    model: model.Model,
    source_definitions: list[dict[str, Any]]
    | None
    | _SourceDefinitionsUnset = _SOURCE_DEFINITIONS_UNSET,
    existing_source: m.ExternalModelSource | None = None,
    metadata_location: str | None = None,
) -> m.ModelEntity:
    plugin = factory.get_plugin_for_data_source(data_source, model=model)
    metadata = plugin.get_table_metadata(source_location)
    source_object = metadata.source_object

    attributes: list[at.Attribute] = []
    source_attribute_mapping: list[m.SourceAttributeMapping] = []

    for field in metadata.iter_source_fields():
        mapped_data_type = plugin.resolve_source_type(field.dataType)
        attribute_types = model.attributeTypes.get_many_where(
            lambda x: (
                x.entity.defaultType == mapped_data_type and x.entity.isDefaultProperty or False
            )
        )

        if len(attribute_types) != 1:
            raise utils.create_error(
                f"No or more than one default attribute type found for {mapped_data_type}: "
                f"{[at.entity.name for at in attribute_types]}"
            )

        attr = at.Attribute(
            ordinalNumber=field.ordinal,
            name=field.name,
            attributeType=attribute_types[0].entity.name,
            dataType=dt.DataType(
                type=mapped_data_type,
                nullable=field.isNullable,
                precision=field.numericPrecision,
                scale=field.numbericScale,
                charLen=field.maxLength,
            ),
            isBusinessKey=field.isPrimaryKey,
            description=field.description,
            dateAdded=datetime.now(UTC),
            properties=field.properties,
        )
        sam = m.SourceAttributeMapping(
            sourceName=field.name,
            targetName=field.name,
            sourceDataType=dt.DataType(
                type=field.dataType,
                nullable=field.isNullable,
                precision=field.numericPrecision,
                scale=field.numbericScale,
                charLen=field.maxLength,
            ),
            properties=field.properties,
        )
        attributes.append(attr)
        source_attribute_mapping.append(sam)

    if isinstance(source_definitions, _SourceDefinitionsUnset):
        source_definitions = plugin.get_sources(source_location)
    source_metadata_location = metadata_location or source_location
    sources = (
        _sources_from_definitions(
            source_definitions, data_source, metadata_location=source_metadata_location
        )
        if source_definitions is not None
        else _default_source(
            data_source,
            existing_source.sourceLocation if existing_source is not None else source_location,
            source_attribute_mapping,
            existing_source=existing_source,
            metadata_location=metadata_location,
        )
    )

    attribute_names = {attr.name for attr in attributes}
    unknown_targets = {
        mapping.targetName
        for external_source in sources
        for mapping in external_source.mapping or []
        if mapping.targetName not in attribute_names
    }
    if unknown_targets:
        raise utils.create_error(
            ValueError(f"Unknown target attributes: {', '.join(sorted(unknown_targets))}")
        )

    entity = m.ModelEntity(
        # name and id are placeholders htat will be replace by model.add_entity()
        name="temp",
        id=1,
        description=source_object.description,
        attributes=attributes,
        properties=source_object.properties,
        sources=sources,
        transformations=[],
        relationships=[],
    )

    return entity


def read_external_sources(
    data_source: str,
    source_location: str,
    /,
    *,
    model: model.Model,
    current_source: m.ExternalModelSource | None = None,
    metadata_location: str | None = None,
) -> list[m.ExternalModelSource]:
    plugin = factory.get_plugin_for_data_source(data_source, model=model)
    source_definitions = plugin.get_sources(source_location)
    if source_definitions is not None:
        return _sources_from_definitions(
            source_definitions, data_source, metadata_location=metadata_location or source_location
        )

    metadata = plugin.get_table_metadata(source_location)
    source_attribute_mapping = [
        m.SourceAttributeMapping(
            sourceName=field.name,
            targetName=field.name,
            sourceDataType=dt.DataType(
                type=field.dataType,
                nullable=field.isNullable,
                precision=field.numericPrecision,
                scale=field.numbericScale,
                charLen=field.maxLength,
            ),
            properties=field.properties,
        )
        for field in metadata.iter_source_fields()
    ]
    return _default_source(
        data_source,
        current_source.sourceLocation if current_source is not None else source_location,
        source_attribute_mapping,
        existing_source=current_source,
        metadata_location=metadata_location,
    )
