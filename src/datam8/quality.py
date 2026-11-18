"""Tool-neutral quality invariants shared by editing, validation and generation."""

from __future__ import annotations

import math
from typing import Any

from datam8.errors import Datam8ValidationError


def _finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_json(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    return True


def validate_quality(entity: Any, locator: str | None = None) -> None:
    """Validate common invariants without interpreting a target's rule dialect."""
    quality = getattr(entity, "quality", None)
    if quality is None:
        return
    value = quality.model_dump(mode="json", exclude_none=True)
    locator = locator or f"modelEntities/{entity.name}"
    seen: set[str] = set()

    def reject(message: str, field: str, check_id: str | None = None) -> None:
        raise Datam8ValidationError(
            message=f"{locator}: {message}",
            details={"locator": locator, "checkId": check_id, "field": field},
        )

    if not _finite_json(value):
        reject("Quality configuration must contain finite JSON values", "quality")
    settings = value.get("settings", {})
    if "maxFailureRatePct" in settings:
        threshold = settings["maxFailureRatePct"]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 100
        ):
            reject(
                "Failure percentage must be between 0 and 100", "quality.settings.maxFailureRatePct"
            )
    for alias, reference in value.get("referenceDatasets", {}).items():
        if not alias.strip():
            reject("Reference aliases must not be blank", "quality.referenceDatasets." + alias)
        entity_id = reference.get("entityId")
        if "entityId" in reference and (
            isinstance(entity_id, bool) or not isinstance(entity_id, int) or entity_id < 0
        ):
            reject(
                "Reference entityId must be a nonnegative integer",
                "quality.referenceDatasets." + alias,
            )
        if "execution" in reference and reference["execution"] not in ("enforcement", "monitoring"):
            reject(
                "Reference execution must be enforcement or monitoring",
                "quality.referenceDatasets." + alias,
            )
    for check in value["checks"]:
        check_id = check["id"]
        if check_id in seen:
            reject(
                f"Duplicate quality check ID '{check_id}'",
                f"quality.checks.{check_id}.id",
                check_id,
            )
        seen.add(check_id)


def validate_model_quality(model: Any) -> None:
    active_ids = {w.entity.id for w in model.modelEntities.values() if not w.is_deleted}
    for wrapper in model.modelEntities.values():
        if wrapper.is_deleted:
            continue
        validate_quality(wrapper.entity, str(wrapper.locator))
        quality = getattr(wrapper.entity, "quality", None)
        if quality is None:
            continue
        references = quality.model_dump(mode="json", exclude_none=True).get("referenceDatasets", {})
        for alias, reference in references.items():
            if "entityId" in reference and reference["entityId"] not in active_ids:
                raise Datam8ValidationError(
                    message=f"{wrapper.locator}: Invalid quality reference '{alias}'",
                    details={
                        "locator": str(wrapper.locator),
                        "field": "quality.referenceDatasets." + alias,
                    },
                )
