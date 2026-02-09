from __future__ import annotations

import time
from pathlib import Path
from typing import Any, TypedDict

from pydantic import ValidationError as PydanticValidationError
from pydantic_core import ValidationError as PydanticCoreValidationError

from datam8 import config, model_exceptions, parser, parser_exceptions
from datam8.factory import create_undefined_folders
from datam8.model import Model
from datam8_model import base as b
from datam8_model.solution import Solution


class ValidationSummary(TypedDict):
    entitiesParsed: int
    modelEntitiesParsed: int
    baseEntitiesParsed: int


class ValidationErrorItem(TypedDict, total=False):
    code: str
    message: str
    path: str
    entityLocator: str
    details: Any


class ValidationReport(TypedDict):
    ok: bool
    dm8sPath: str
    summary: ValidationSummary
    errors: list[ValidationErrorItem]
    warnings: list[str]
    durationMs: int


def _new_report(dm8s_path: Path) -> ValidationReport:
    return {
        "ok": False,
        "dm8sPath": str(dm8s_path),
        "summary": {
            "entitiesParsed": 0,
            "modelEntitiesParsed": 0,
            "baseEntitiesParsed": 0,
        },
        "errors": [],
        "warnings": [],
        "durationMs": 0,
    }


def _model_summary(parsed_model: Model) -> ValidationSummary:
    model_entities = len(parsed_model.modelEntities)
    base_entities = sum(
        len(getattr(parsed_model, entity_type.value))
        for entity_type in b.EntityType
        if entity_type is not b.EntityType.MODEL_ENTITIES
    )
    return {
        "entitiesParsed": model_entities + base_entities,
        "modelEntitiesParsed": model_entities,
        "baseEntitiesParsed": base_entities,
    }


def _append_error(
    report: ValidationReport,
    *,
    code: str,
    message: str,
    path: str | None = None,
    entity_locator: str | None = None,
    details: Any = None,
) -> None:
    item: ValidationErrorItem = {
        "code": code,
        "message": message,
    }
    if path:
        item["path"] = path
    if entity_locator:
        item["entityLocator"] = entity_locator
    if details is not None:
        item["details"] = details
    report["errors"].append(item)


def _append_pydantic_error(
    report: ValidationReport,
    *,
    code: str,
    err: PydanticValidationError | PydanticCoreValidationError,
    path: str | None = None,
) -> None:
    details: Any
    if hasattr(err, "errors"):
        try:
            details = err.errors()
        except Exception:
            details = str(err)
    else:
        details = str(err)
    _append_error(report, code=code, message=str(err), path=path, details=details)


async def validate_solution_dm8s(dm8s_path: Path) -> ValidationReport:
    """
    Validate a DataM8 solution using the same parse + resolve pipeline as the CLI.

    The function never raises SystemExit and always returns a JSON-serializable report.
    """
    started = time.perf_counter()
    report = _new_report(dm8s_path)

    try:
        if dm8s_path.suffix.lower() != ".dm8s":
            raise ValueError("Validation expects a .dm8s solution file path.")
        if not dm8s_path.exists():
            raise FileNotFoundError(f"Solution file not found: {dm8s_path}")

        dm8s_path = dm8s_path.resolve()
        report["dm8sPath"] = str(dm8s_path)

        config.solution_path = dm8s_path
        config.solution_folder_path = dm8s_path.parent
        config.lazy = False

        # Keep the explicit solution parsing step aligned with CLI validation behavior.
        _ = Solution.from_json_file(dm8s_path)

        parsed_model = await parser.parse_full_solution_async(dm8s_path)
        create_undefined_folders(parsed_model)
        parsed_model.resolve()

        report["summary"] = _model_summary(parsed_model)
        report["ok"] = True
    except (PydanticValidationError, PydanticCoreValidationError) as err:
        _append_pydantic_error(report, code="SCHEMA_ERROR", err=err, path=str(dm8s_path))
    except parser_exceptions.NotSupportedModelVersion as err:
        _append_error(
            report,
            code="SCHEMA_ERROR",
            message=str(err),
            path=str(dm8s_path),
            details={"supportedModelVersions": list(config.supported_model_versions)},
        )
    except parser_exceptions.ModelParseException as err:
        if err.inner_exceptions:
            for inner in err.inner_exceptions:
                if isinstance(inner, (PydanticValidationError, PydanticCoreValidationError)):
                    _append_pydantic_error(report, code="SCHEMA_ERROR", err=inner)
                else:
                    _append_error(
                        report,
                        code="PARSING_ERROR",
                        message=str(inner),
                        details={"type": type(inner).__name__},
                    )
        else:
            _append_error(report, code="PARSING_ERROR", message=str(err))
    except (model_exceptions.EntityNotFoundError, model_exceptions.PropertiesNotResolvedError, RecursionError) as err:
        _append_error(
            report,
            code="RESOLVE_ERROR",
            message=str(err),
            details={"type": type(err).__name__},
        )
    except UnicodeError as err:
        _append_error(
            report,
            code="UNKNOWN_ERROR",
            message=f"Console encoding error: {err}",
            path=str(dm8s_path),
            details={"type": type(err).__name__},
        )
    except (FileNotFoundError, ValueError) as err:
        _append_error(
            report,
            code="PARSING_ERROR",
            message=str(err),
            path=str(dm8s_path),
            details={"type": type(err).__name__},
        )
    except Exception as err:
        _append_error(
            report,
            code="UNKNOWN_ERROR",
            message=str(err) or "Unexpected validation error.",
            details={"type": type(err).__name__},
        )
    finally:
        report["durationMs"] = int((time.perf_counter() - started) * 1000)

    return report
