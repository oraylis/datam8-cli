import datetime
import logging
import pathlib
import json
from collections.abc import MutableSequence, Sequence
from typing import overload

from datam8 import parser_v1, utils
from datam8_model import (  # noqa: I001
    attribute as a,
)
from datam8_model import (
    base as b,
)
from datam8_model import (
    common as c,
)
from datam8_model import (
    data_product as dp,
)
from datam8_model import (
    data_source as ds,
)
from datam8_model import (
    data_type as dt,
)
from datam8_model import (
    diagram as d,
)
from datam8_model import (
    folder as f,
)
from datam8_model import (
    model as m,
)
from datam8_model import (
    property as p,
)
from datam8_model import (
    zone as z,
)
from datam8_model import solution as s
from datam8_model.v1 import (
    AttributeTypes as at_legacy,
    Solution,
)
from datam8_model.v1 import (
    CoreModelEntry as core_legacy,
)
from datam8_model.v1 import (
    CuratedModelEntry as curated_legacy,
)
from datam8_model.v1 import (
    DataProducts as dp_legacy,
)
from datam8_model.v1 import (
    DataSources as ds_legacy,
)
from datam8_model.v1 import (
    DataTypes as dt_legacy,
)
from datam8_model.v1 import (
    RawModelEntry as raw_legacy,
)
from datam8_model.v1 import (
    StageModelEntry as stage_legacy,
)

logger = logging.getLogger(__name__)

entity_id_counter = 0

MODEL_DUMP_OPTIONS = {"indent": 2, "exclude_defaults": True, "exclude_none": True}

type BaseEntitiesType = (
    ds_legacy.Model | at_legacy.Model | dp_legacy.Model | dt_legacy.Model
)

type Tags = Sequence[str]


def data_source(old: ds_legacy.DataSource) -> ds.DataSource:
    if old.name is None or old.type is None:
        raise MigrationError("name|type")

    if old.dataTypeMapping is None:
        new_mapping = []
    else:
        new_mapping = [data_type_mapping(dtm) for dtm in old.dataTypeMapping]

    new = ds.DataSource(
        name=old.name,
        type=old.type,
        displayName=old.displayName,
        description=old.purpose,
        connectionString=old.connectionString,
        dataTypeMapping=new_mapping,
    )

    return new


def data_type_mapping(
    old: ds_legacy.DataTypeMappingItem,
) -> ds.SourceDataTypeMapping:
    if old.sourceType is None or old.targetType is None:
        raise MigrationError("sourceType|targetType")

    new = ds.SourceDataTypeMapping(
        sourceType=old.sourceType,
        targetType=old.targetType,
    )

    return new


def attribute_type(old: at_legacy.AttributeType) -> a.AttributeType:
    if (
        old.isUnit == at_legacy.IsUnit.CURRENCY
        or old.hasUnit == at_legacy.HasUnit.CURRENCY
    ):
        has_unit = a.HasUnit.CURRENCY
    elif (
        old.isUnit == at_legacy.IsUnit.PHYSICAL
        or old.hasUnit == at_legacy.IsUnit.PHYSICAL
    ):
        has_unit = a.HasUnit.PHYSICAL
    else:
        has_unit = a.HasUnit.NO_UNIT

    new = a.AttributeType(
        name=old.name,
        displayName=old.displayName,
        description=_compose_description(old.purpose, old.explanation),
        defaultType=old.defaultType,
        defaultLength=old.defaultLength,
        defaultPrecision=old.defaultPrecision,
        defaultScale=old.defaultScale,
        hasUnit=has_unit,
        canBeInRelation=old.canBeInRelation,
        isDefaultProperty=old.isDefaultProperty,
    )

    return new


def data_module(old: dp_legacy.DataModule) -> dp.DataModule:
    if old.name is None:
        raise MigrationError("name")

    new = dp.DataModule(
        name=old.name,
        displayName=old.displayName,
        description=_compose_description(old.purpose, old.explanation),
    )

    return new


def data_product(old: dp_legacy.DataProduct) -> dp.DataProduct:
    if old.module is None or old.name is None:
        raise MigrationError("module|name")

    new = dp.DataProduct(
        name=old.name,
        displayName=old.displayName,
        dataModules=[data_module(dm) for dm in old.module],
        description=_compose_description(old.purpose, old.explanation),
    )

    return new


def _compose_description(purpose: str | None, explanation: str | None) -> str | None:
    if purpose and explanation:
        return f"{purpose}\n{explanation}"
    elif purpose is None:
        return explanation
    elif explanation is None:
        return purpose

    return None


def data_type(old: dt_legacy.DataType) -> dt.DataTypeDefinition:
    targets = {
        "databricks": old.parquetType,
    }

    new = dt.DataTypeDefinition(
        name=old.name,
        displayName=old.displayName,
        description=_compose_description(old.purpose, None),
        hasCharLen=old.hasCharLen,
        hasPrecision=old.hasPrecision,
        hasScale=old.hasScale,
        targets=targets,
    )

    return new


@overload
def base_entities(old: at_legacy.Model) -> b.AttributeTypes: ...
@overload
def base_entities(old: ds_legacy.Model) -> b.DataSources: ...
@overload
def base_entities(old: dp_legacy.Model) -> b.DataProducts: ...
@overload
def base_entities(old: dt_legacy.Model) -> b.DataTypes: ...


def base_entities(old: BaseEntitiesType) -> b.BaseEntitiesType:
    if old.items is None:
        raise MigrationError("items")

    match old:
        case at_legacy.Model():
            return b.AttributeTypes(
                type=b.EntityType.ATTRIBUTE_TYPES.value,
                attributeTypes=[attribute_type(at) for at in old.items],
            )
        case ds_legacy.Model():
            return b.DataSources(
                type=b.EntityType.DATA_SOURCES.value,
                dataSources=[data_source(ds) for ds in old.items],
            )
        case dp_legacy.Model():
            return b.DataProducts(
                type=b.EntityType.DATA_PRODUCTS.value,
                dataProducts=[data_product(dp) for dp in old.items],
            )
        case dt_legacy.Model():
            return b.DataTypes(
                type=b.EntityType.DATA_TYPES.value,
                dataTypes=[data_type(dt) for dt in old.items],
            )


def migrate_base_entities(base_dir_path: pathlib.Path, output_path: pathlib.Path) -> None:
    utils.mkdir(output_path, recursive=True)

    for file in base_dir_path.glob("*.json"):
        output_file_path = output_path / utils.pascal_to_snake_case(file.name)

        logger.debug(f"Migrating {file} to {output_file_path}")

        match file.name:
            case "DataTypes.json":
                base_entity = dt_legacy.Model.from_json_file(file)
            case "DataProducts.json":
                base_entity = dp_legacy.Model.from_json_file(file)
            case "AttributeTypes.json":
                base_entity = at_legacy.Model.from_json_file(file)
            case "DataSources.json":
                base_entity = ds_legacy.Model.from_json_file(file)
            case _:
                logger.warning(
                    "Unknown base file found, cannot be migrated: %s", file.name
                )
                continue

        content = base_entities(base_entity).model_dump_json(indent=2, exclude_none=True)

        with open(output_file_path, "w") as file:
            file.write(content)

    logger.info(
        f"Migrated base entities from {base_dir_path.as_posix()} to {output_path.as_posix()}"
    )


@overload
def model_entities(old: raw_legacy.Model) -> m.ModelEntity: ...
@overload
def model_entities(old: stage_legacy.Model) -> m.ModelEntity: ...
@overload
def model_entities(old: core_legacy.Model) -> m.ModelEntity: ...
@overload
def model_entities(old: curated_legacy.Model) -> m.ModelEntity: ...


def model_entities(old: parser_v1.ModelEntitiesType) -> m.ModelEntity:
    match old:
        case raw_legacy.Model():
            raise NotImplementedError()
        case stage_legacy.Model():
            raise NotImplementedError()
        case core_legacy.Model():
            return core_entity(old)
        case curated_legacy.Model():
            raise NotImplementedError()


def migrate_model_entities(
    model_dir_path: pathlib.Path, output_path: pathlib.Path
) -> Tags:
    """
    Migrate tags from a directory and return all used tags
    """

    tags: list[str] = []

    for file in model_dir_path.glob("**/*.json"):
        output_file_path = (
            output_path
            / file.parent.relative_to(model_dir_path.absolute())
            / utils.pascal_to_snake_case(file.name)
        )

        logger.debug(f"Migrating {file} to {output_file_path}")

        model_entity = parser_v1.parse_model_file(file)
        content = model_entities(model_entity).model_dump_json(
            indent=2, exclude_none=True, exclude_defaults=True
        )

        utils.mkdir(output_file_path.parent, recursive=True)

        if model_entity.entity:
            tags.extend(model_entity.entity.tags or [])

        with open(output_file_path, "w") as file:
            file.write(content)

    logger.info(
        f"Migrated model entities from {model_dir_path.as_posix()} to {output_path.as_posix()}"
    )

    return tags


def migrate_zones(solution: Solution.Model, output_path: pathlib.Path) -> None:
    new_zones = b.Zones(
        type="zones",
        zones=[
            z.Zone(
                name="Stage",
                displayName=solution.AreaTypes_1.Stage,
                targetName="Stage",
            ),
            z.Zone(
                name="Core",
                displayName=solution.AreaTypes_1.Core,
                targetName="Core",
            ),
            z.Zone(
                name="Curated",
                displayName=solution.AreaTypes_1.Curated,
                targetName="Curated",
            ),
        ],
    )
    content = new_zones.model_dump_json(
        indent=2, exclude_defaults=True, exclude_none=True
    )

    with open(output_path, "w") as file:
        file.write(content)


def create_new_databricks_solution(output_path: pathlib.Path) -> None:
    new_soution = s.Solution(
        schemaVersion="2.0.0",
        basePath=pathlib.Path("Base"),
        modelPath=pathlib.Path("Model"),
        generatorTargets=[
            s.GeneratorTarget(
                name="databricks",
                sourcePath=pathlib.Path("Generate/databricks-lake"),
                outputPath=pathlib.Path("Output"),
                isDefault=True,
            )
        ],
    )
    content = new_soution.model_dump_json(**MODEL_DUMP_OPTIONS)

    with open(output_path, "w") as file:
        file.write(content)


def create_new_properties(tags: Tags, output_path: pathlib.Path) -> None:
    new_properties = b.Properties(
        type="properties",
        properties=[
            p.Property(name="tags", displayName="Tags"),
            p.Property(name="column_type", displayName="Column Type"),
        ],
    )
    new_property_values = b.PropertyValues(
        type="propertyValues",
        propertyValues=[
            p.PropertyValue(
                name=tag,
                property="tags",
            )
            for tag in tags
        ],
    )

    with open(output_path / "properties.json", "w") as file:
        file.write(new_properties.model_dump_json(**MODEL_DUMP_OPTIONS))

    with open(output_path / "property_values.json", "w") as file:
        file.write(new_property_values.model_dump_json(**MODEL_DUMP_OPTIONS))


def get_dm8l_source(
    sources: Sequence[core_legacy.SourceEntity] | None,
) -> dict[str, core_legacy.MappingItem]:
    attributes: dict[str, core_legacy.MappingItem] = {}

    for src in sources or []:
        if src.dm8l == "#":
            for attr in src.mapping or []:
                if attr.name is None:
                    raise MigrationError("name")

                attributes[attr.name] = attr
            break

    return attributes


def core_entity(old: core_legacy.Model) -> m.ModelEntity:
    if old.entity is None or old.function is None:
        raise MigrationError("entity|function")

    if old.entity.attribute is None:
        raise MigrationError("entity.attribute")

    global entity_id_counter
    entity_id_counter += 1

    attribute_mappings = get_dm8l_source(old.function.source)

    attributes: list[a.Attribute] = []
    source_mappings: list[m.InternalModelSource] = []
    ordinal_number = 0

    for attr in old.entity.attribute:
        ordinal_number += 1
        new_attribute = attribute(attr)
        new_attribute.ordinalNumber = ordinal_number

        if attr.name in attribute_mappings:
            source_computation = attribute_mappings[attr.name].sourceComputation
            new_attribute.expression = (
                source_computation if source_computation != "Default" else None
            )

        attributes.append(new_attribute)

    for src in old.function.source or []:
        if src.dm8l == "#":
            continue

        source_mapping = [
            m.SourceAttributeMapping(
                sourceName=mapping.sourceName,
                targetName=mapping.name,
            )
            for mapping in src.mapping or []
            if mapping.name is not None and mapping.name != mapping.sourceName
        ]

        new_source = m.InternalModelSource(
            sourceLocation=src.dm8l,
            mapping=source_mapping if len(source_mapping) > 0 else None,
        )

        source_mappings.append(new_source)

    relationships: list[m.ModelRelationship] = []
    for rel in old.entity.relationship or []:
        new_relationship = m.ModelRelationship(
            targetLocation=rel.dm8lKey,
            alias=rel.role if rel.role != "#" else None,
            attributes=[
                m.ModelAttributeMapping(
                    sourceName=attr.dm8lKeyAttr, targetName=attr.dm8lAttr
                )
                for attr in rel.fields or []
            ],
        )
        relationships.append(new_relationship)

    new = m.ModelEntity(
        id=entity_id_counter,
        name=old.entity.name,
        displayName=old.entity.displayName,
        description=_compose_description(old.entity.purpose, old.entity.explanation),
        parameters=[
            m.ModelParameter(name=p.name, value=p.value)
            for p in old.entity.parameters or []
        ],
        properties=[
            p.PropertyReference(property="tags", value=tag)
            for tag in old.entity.tags or []
        ],
        attributes=attributes,
        sources=source_mappings,
        transformations=[],
        relationships=relationships,
    )

    return new


def attribute(old: core_legacy.Attribute) -> a.Attribute:
    if old.dataType is None or old.attributeType is None:
        raise MigrationError("dataType|attributeType")

    history: a.HistoryType = a.HistoryType.SCD0
    old_history = old.history or core_legacy.History.SCD1

    if old_history.value in a.HistoryType._value2member_map_:
        history = a.HistoryType(old_history.value)

    properties = [
        p.PropertyReference(property="tags", value=tag) for tag in old.tags or []
    ]

    if old.history == core_legacy.History.SK:
        properties.append(p.PropertyReference(property="column_type", value="SK"))

    new = a.Attribute(
        name=old.name,
        displayName=old.displayName,
        description=_compose_description(old.purpose, old.explanation),
        ordinalNumber=1,
        attributeType=old.attributeType,
        isBusinessKey=True if old.businessKeyNo else False,
        properties=properties if properties else None,
        history=history,
        dataType=dt.DataType(
            type=old.dataType,
            nullable=old.nullable or False,
            charLen=old.charLength,
            precision=old.precision,
            scale=old.scale,
        ),
        dateAdded=datetime.datetime.now(),
        dateDeleted=None,
        dateModified=None,
        refactorNames=old.refactorNames if old.refactorNames else None,
    )

    return new


class MigrationError(Exception):
    def __init__(self, attr: str):
        super().__init__(f"Attribute {attr} cannot be None")
