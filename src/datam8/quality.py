"""Structural quality contract; target engines interpret SQL and native functions."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from datam8.errors import Datam8ValidationError

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_quality_value(value: Any, locator: str | None = None) -> dict[str, Any]:
    """Validate raw values before model coercion, without interpreting SQL."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_unset=True)

    def reject(message: str, field: str, check_id: str | None = None) -> None:
        raise Datam8ValidationError(
            message=f"{locator or 'Quality'}: {message}",
            details={"locator": locator, "checkId": check_id, "field": field},
        )

    if not isinstance(value, Mapping) or "checks" not in value:
        reject("Quality requires a checks list", "quality")
    unknown = set(value) - {"checks", "maxFailureRatePct", "references"}
    if unknown:
        reject("Unsupported quality fields: " + ", ".join(sorted(unknown)), "quality")
    if not isinstance(value["checks"], (list, tuple)):
        reject("Quality checks must be a list", "quality.checks")
    if "maxFailureRatePct" in value:
        threshold = value["maxFailureRatePct"]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 100
        ):
            reject(
                "Failure percentage must be a finite number between 0 and 100",
                "quality.maxFailureRatePct",
            )
    if "references" in value:
        if not isinstance(value["references"], Mapping):
            reject("References must be named entity bindings", "quality.references")
        for alias, binding in value["references"].items():
            if hasattr(binding, "model_dump"):
                binding = binding.model_dump(mode="json", exclude_unset=True)
            if not isinstance(alias, str) or not _IDENTIFIER.fullmatch(alias):
                reject("Invalid reference alias", "quality.references")
            field = "quality.references." + alias
            if not isinstance(binding, Mapping) or set(binding) != {"entityId"}:
                reject("References require exactly entityId", field)
            entity_id = binding["entityId"]
            if isinstance(entity_id, bool) or not isinstance(entity_id, int) or entity_id < 0:
                reject("Reference entityId must be a nonnegative integer", field)
    seen: set[str] = set()
    allowed = {
        "id",
        "execution",
        "expression",
        "function",
        "arguments",
        "severity",
        "description",
        "sql",
        "onEmpty",
    }
    for check in value["checks"]:
        if hasattr(check, "model_dump"):
            check = check.model_dump(mode="json", exclude_unset=True)
        if not isinstance(check, Mapping):
            reject("Each check must be an object", "quality.checks")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not _IDENTIFIER.fullmatch(check_id):
            reject("Invalid check ID", "quality.checks.id")
        field = "quality.checks." + check_id
        if check_id in seen:
            reject("Duplicate quality check ID '" + check_id + "'", field + ".id", check_id)
        seen.add(check_id)
        unknown = set(check) - allowed
        if unknown:
            reject("Unsupported check fields: " + ", ".join(sorted(unknown)), field, check_id)
        if check.get("execution") not in ("enforcement", "monitoring"):
            reject("Execution must be enforcement or monitoring", field + ".execution", check_id)
        if ("expression" in check) == ("function" in check):
            reject("Exactly one of expression or function is required", field, check_id)
        if "arguments" in check and (
            "function" not in check or not isinstance(check["arguments"], dict)
        ):
            reject(
                "arguments requires function and must be a JSON object",
                field + ".arguments",
                check_id,
            )
        for key in ("expression", "function", "sql"):
            if key in check:
                if not isinstance(check.get(key), str) or not check[key].strip():
                    reject(key + " must be a nonblank string", field + "." + key, check_id)
        if "severity" in check and check["severity"] not in ("error", "warning"):
            reject("Severity must be error or warning", field + ".severity", check_id)
        if "description" in check and not isinstance(check["description"], str):
            reject("Description must be a string", field + ".description", check_id)
        if "sql" in check and check["execution"] != "monitoring":
            reject("sql is only allowed for monitoring", field + ".sql", check_id)
        if "onEmpty" in check and (
            "sql" not in check or check["onEmpty"] not in ("evaluate", "no_data")
        ):
            reject(
                "onEmpty requires sql and must be evaluate or no_data", field + ".onEmpty", check_id
            )
    return dict(value)


def validate_quality(entity: Any, locator: str | None = None) -> None:
    quality = getattr(entity, "quality", None)
    if quality is not None:
        validate_quality_value(quality, locator or f"modelEntities/{entity.name}")


def validate_model_quality(model: Any) -> None:
    active_ids = {w.entity.id for w in model.modelEntities.values() if not w.is_deleted}
    for wrapper in model.modelEntities.values():
        if wrapper.is_deleted:
            continue
        validate_quality(wrapper.entity, str(wrapper.locator))
        quality = getattr(wrapper.entity, "quality", None)
        if quality is None:
            continue
        references = quality.model_dump(mode="json", exclude_none=True).get("references", {})
        for alias, reference in references.items():
            if reference["entityId"] not in active_ids:
                raise Datam8ValidationError(
                    message=f"{wrapper.locator}: Invalid quality reference '{alias}'",
                    details={
                        "locator": str(wrapper.locator),
                        "field": "quality.references." + alias,
                    },
                )
