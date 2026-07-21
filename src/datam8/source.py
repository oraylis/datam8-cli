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
from typing import Any

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


def compare_entity_with_source(
    locator: l.LocatorOrString, /, *, model: model.Model | None = None
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

    attribute_index = {
        wrapper.entity.attributes[idx].name: idx for idx in range(0, len(wrapper.entity.attributes))
    }
    current_attributes = [attr.model_copy(deep=True) for attr in wrapper.entity.attributes]
    source_entities: dict[str, m.ModelEntity] = {}

    for source in wrapper.entity.sources:
        # refresh is only relevant for external sources
        if isinstance(source, m.InternalModelSource):
            continue

        modified_date = datetime.now(UTC)

        # get current source definition from model and live from the source
        source_entities[f"{source.dataSource}|{source.sourceLocation}"] = (
            source_entity := read_from_data_source(
                source.dataSource, source.sourceLocation, model=model_
            )
        )
        current_mapping: dict[str, m.SourceAttributeMapping] = {
            f"{f.sourceName}|{f.targetName}": f for f in source.mapping or []
        }
        refreshed_mapping: dict[str, m.SourceAttributeMapping] = {
            f"{col_mapping.sourceName}|{col_mapping.targetName}": col_mapping
            for refreshed_source in source_entity.sources
            if isinstance(refreshed_source, m.ExternalModelSource)
            and refreshed_source.sourceLocation == source.sourceLocation
            and refreshed_source.dataSource == source.dataSource
            and refreshed_source.mapping is not None
            for col_mapping in refreshed_source.mapping
        }

        # enrich the live source mappings with properties etc. that are already set in the model
        for key, val in current_mapping.items():
            if key not in refreshed_mapping:
                continue

            property_refs: list[p.PropertyReference] = list(refreshed_mapping[key].properties or [])
            # only add new properties from the source, keep existing ones the same
            property_refs.extend(
                [prop for prop in val.properties or [] if prop not in property_refs]
            )

            refreshed_mapping[key].properties = property_refs if len(property_refs) > 0 else None

            if property_refs != (val.properties or []):
                current_attributes[attribute_index[val.targetName]].dateModified = modified_date

        source.mapping = list(refreshed_mapping.values())

    # check for new attributes/source mappings and add them to the wrapper
    current_attributes.extend(
        [
            attr
            for source_entity in source_entities.values()
            for attr in source_entity.attributes
            if attr.name not in [ex.name for ex in current_attributes]
        ]
    )

    # cleanup attribute list (remove non-referenced attributes and update ordinal number)
    current_attributes.sort(key=lambda attr: attr.ordinalNumber)
    current_attributes = [
        attr
        for attr in current_attributes
        if any(
            [
                attr.name in map.targetName
                for src in wrapper.entity.sources
                if isinstance(src, m.ExternalModelSource) and src.mapping is not None
                for map in src.mapping
            ]
        )
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

    diff = DeepDiff(
        original_entity.model_dump(mode="json", exclude_none=True),
        wrapper.entity.model_dump(mode="json", exclude_none=True),
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
    data_source: str, source_location: str, /, *, model: model.Model
) -> m.ModelEntity:
    plugin = factory.get_plugin_for_data_source(data_source, model=model)
    metadata = plugin.get_table_metadata(source_location)

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
            dateAdded=datetime.now(UTC),
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

    entity = m.ModelEntity(
        # name and id are placeholders htat will be replace by model.add_entity()
        name="temp",
        id=1,
        attributes=attributes,
        sources=[
            m.ExternalModelSource(
                sourceLocation=source_location,
                dataSource=data_source,
                mapping=source_attribute_mapping,
            )
        ],
        transformations=[],
        relationships=[],
    )

    return entity
