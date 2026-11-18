"""Platform-neutral quality semantics shared by editing, validation and generation."""

from __future__ import annotations

import math
from typing import Any

from datam8.errors import Datam8ValidationError

NUMERIC_TYPES = {
    "byte",
    "short",
    "int",
    "integer",
    "long",
    "bigint",
    "smallint",
    "tinyint",
    "int8",
    "int16",
    "int32",
    "int64",
    "float",
    "double",
    "decimal",
    "numeric",
    "number",
}
TIMESTAMP_TYPES = {"timestamp", "datetime", "datetime2", "datetimeoffset", "timestamp_ntz"}


def validate_quality(entity: Any, locator: str | None = None) -> None:
    """Validate cross-field requirements without modifying the candidate entity."""
    quality = getattr(entity, "quality", None)
    if quality is None:
        return
    value = quality.model_dump(mode="json", exclude_none=True)
    locator = locator or f"modelEntities/{entity.name}"
    attributes = {a.name: a for a in entity.attributes if not a.dateDeleted}
    seen: set[str] = set()

    def reject(message: str, field: str, check_id: str | None = None) -> None:
        raise Datam8ValidationError(
            message=f"{locator}: {message}",
            details={"locator": locator, "checkId": check_id, "field": field},
        )

    threshold = value.get("settings", {}).get("maxFailureRatePct")
    if threshold is not None and not math.isfinite(threshold):
        reject("Failure percentage must be finite", "quality.settings.maxFailureRatePct")
    if any(
        not requirement.strip() for requirement in value.get("settings", {}).get("dependencies", [])
    ):
        reject("Dependencies must not be blank", "quality.settings.dependencies")
    for alias, reference in value.get("referenceDatasets", {}).items():
        if not alias.strip() or ("table" in reference and not reference["table"].strip()):
            reject(
                "Reference aliases and table names must not be blank",
                "quality.referenceDatasets." + alias,
            )
    for check in value["checks"]:
        check_id = check["id"]
        field = f"quality.checks.{check_id}"
        if check_id in seen:
            reject(f"Duplicate quality check ID '{check_id}'", field + ".id", check_id)
        seen.add(check_id)
        if check["type"] == "dqx":
            definition = check["definition"]
            if not definition["check"]["function"].strip():
                reject(
                    "DQX function must not be blank", field + ".definition.check.function", check_id
                )
            metadata = definition.get("user_metadata") or {}
            if "datam8_check_id" in metadata and str(metadata["datam8_check_id"]) != check_id:
                reject(
                    "datam8_check_id is reserved for the rule ID",
                    field + ".definition.user_metadata",
                    check_id,
                )

            # DQX owns function/argument validity. Do not maintain a DataM8 function allow-list.
            def finite_json(value: Any) -> bool:
                if isinstance(value, float):
                    return math.isfinite(value)
                if isinstance(value, dict):
                    return all(finite_json(v) for v in value.values())
                if isinstance(value, list):
                    return all(finite_json(v) for v in value)
                return True

            if not finite_json(definition):
                reject(
                    "DQX definition must contain finite JSON values",
                    field + ".definition",
                    check_id,
                )
            continue
        attribute = check.get("attribute")
        if attribute is not None and attribute not in attributes:
            reject(
                f"Quality check '{check_id}' references missing/deleted attribute '{attribute}'",
                field + ".attribute",
                check_id,
            )
        params = check.get("parameters", {})
        if any(isinstance(v, (int, float)) and not math.isfinite(v) for v in params.values()):
            reject("Quality bounds must be finite", field + ".parameters", check_id)
        kind = check["type"]
        if kind in ("range", "row_count"):
            low, high = ("min", "max") if kind == "range" else ("minCount", "maxCount")
            if low not in params and high not in params:
                reject("At least one bound is required", field + ".parameters", check_id)
            if low in params and high in params and params[low] > params[high]:
                reject("Minimum must not exceed maximum", field + ".parameters", check_id)
        if kind == "range" and attributes[attribute].dataType.type.lower() not in NUMERIC_TYPES:
            reject("Range requires a numeric attribute", field + ".attribute", check_id)
        if (
            kind == "freshness"
            and attributes[attribute].dataType.type.lower() not in TIMESTAMP_TYPES
        ):
            reject("Freshness requires a timestamp attribute", field + ".attribute", check_id)
        if kind == "sql_expression" and not params["expression"].strip():
            reject("SQL expression must not be blank", field + ".parameters.expression", check_id)


def validate_model_quality(model: Any) -> None:
    active_ids = {w.entity.id for w in model.modelEntities.values() if not w.is_deleted}
    for wrapper in model.modelEntities.values():
        if not wrapper.is_deleted:
            validate_quality(wrapper.entity, str(wrapper.locator))
            quality = getattr(wrapper.entity, "quality", None)
            if quality is None:
                continue
            references = quality.model_dump(mode="json", exclude_none=True).get(
                "referenceDatasets", {}
            )
            for alias, reference in references.items():
                if not alias.strip() or (
                    "entityId" in reference and reference["entityId"] not in active_ids
                ):
                    raise Datam8ValidationError(
                        message=f"{wrapper.locator}: Invalid quality reference '{alias}'",
                        details={
                            "locator": str(wrapper.locator),
                            "field": "quality.referenceDatasets." + alias,
                        },
                    )
