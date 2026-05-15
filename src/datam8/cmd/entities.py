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

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from datam8 import config, factory, logging, model, opts, utils
from datam8_model import base as b
from datam8_model import model as model_types

from . import common

logger = logging.getLogger(__name__)

SetOption = Annotated[
    list[str] | None,
    typer.Option(
        "--set",
        help=(
            "Top-level key=value patch value. May be repeated. Values are parsed as JSON "
            "literals when possible; otherwise they remain strings."
        ),
    ),
]
BodyOption = Annotated[
    Path | None,
    typer.Option("--body", help="Path to a JSON object request body."),
]
JsonBodyOption = Annotated[
    str | None,
    typer.Option("--json-body", help="Inline JSON object request body."),
]
JsonOutputOption = Annotated[bool, typer.Option("--json", help="Emit valid JSON only on stdout.")]
YesOption = Annotated[
    bool,
    typer.Option("--yes", "-y", help="Confirm a destructive operation without prompting."),
]

app = typer.Typer(
    name="entities",
    help="Locator-based entity inspection and mutation commands",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)

import_app = typer.Typer(
    name="import",
    help="Import model entities from external or internal sources",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)
app.add_typer(import_app)


def _load_model_for_cli(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel,
    version: opts.Version,
) -> model.Model:
    common.main_callback(solution_path, log_level, version)
    config.lazy = True
    return factory.create_model_or_exit()


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, default=str, separators=(",", ":")))


def _fail(
    message: str,
    *,
    json_output: bool,
    operation: str,
    locator: str | None = None,
    code: str = "COMMAND_ERROR",
) -> None:
    if json_output:
        payload: dict[str, Any] = {
            "status": "error",
            "operation": operation,
            "error": {"code": code, "message": message},
        }
        if locator is not None:
            payload["locator"] = locator
        _emit_json(payload)
    else:
        typer.echo(message, err=True)
    raise typer.Exit(1)


def _emit_success(payload: dict[str, Any], *, json_output: bool, message: str) -> None:
    if json_output:
        _emit_json(payload)
        return
    typer.echo(message)


def _parse_set_options(set_options: Sequence[str]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for item in set_options:
        if "=" not in item:
            raise ValueError("--set values must use key=value syntax")
        key, value = item.split("=", 1)
        if key == "":
            raise ValueError("--set key must not be empty")
        try:
            body[key] = json.loads(value)
        except json.JSONDecodeError:
            body[key] = value
    return body


def _load_json_body_from_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError(f"Could not read body file: {path}") from err
    return _parse_json_object(raw, f"--body {path}")


def _parse_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError(f"{label} must contain valid JSON") from err
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return parsed


def _parse_body(
    *,
    set_options: Sequence[str] | None,
    body_path: Path | None,
    json_body: str | None,
) -> dict[str, Any]:
    modes = [
        bool(set_options),
        body_path is not None,
        json_body is not None,
    ]
    if sum(modes) == 0:
        raise ValueError("Provide exactly one input mode: --set, --body, or --json-body")
    if sum(modes) > 1:
        raise ValueError("Use only one input mode: --set, --body, or --json-body")
    if set_options:
        return _parse_set_options(set_options)
    if body_path is not None:
        return _load_json_body_from_file(body_path)
    assert json_body is not None
    return _parse_json_object(json_body, "--json-body")


def _model_entity_defaults(locator: str) -> dict[str, Any]:
    loc = model.Locator.from_path(locator)
    now = datetime.now(UTC)
    return {
        "displayName": loc.entityName,
        "attributes": [
            {
                "ordinalNumber": 1,
                "name": "Value",
                "attributeType": "Generic String",
                "dataType": {"type": "string", "nullable": True},
                "dateAdded": now,
            }
        ],
        "sources": [],
        "transformations": [],
        "relationships": [],
    }


def _create_content(locator: str, body: dict[str, Any]) -> dict[str, Any]:
    loc = model.Locator.from_path(locator)
    if loc.entityType != b.EntityType.MODEL_ENTITIES.value:
        return dict(body)
    return {**_model_entity_defaults(locator), **body}


def _metadata_rows(metadata: Any) -> list[dict[str, Any]]:
    if hasattr(metadata, "to_dicts"):
        return list(metadata.to_dicts())

    rows = []
    if hasattr(metadata, "rows"):
        for idx, row in enumerate(metadata.rows(), start=1):
            rows.append(
                {
                    "name": row[0],
                    "ordinal": idx,
                    "dataType": row[4] if len(row) > 4 else "string",
                    "isNullable": row[2] == "YES" if len(row) > 2 else True,
                }
            )
    return rows


def _get_first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def _build_external_import_content(
    *,
    data_source: str,
    schema: str | None,
    table: str,
    metadata: Any,
    display_name: str | None,
    description: str | None,
    source_alias: str | None,
) -> dict[str, Any]:
    source: dict[str, Any] = {
        "dataSource": data_source,
        "sourceLocation": f"[{schema}].[{table}]" if schema else table,
    }
    if source_alias:
        source["sourceAlias"] = source_alias

    now = datetime.now(UTC)
    attributes: list[dict[str, Any]] = []
    mapping: list[dict[str, str]] = []
    for index, row in enumerate(_metadata_rows(metadata), start=1):
        name = str(_get_first(row, "name", "COLUMN_NAME", "column_name"))
        ordinal = int(
            _get_first(row, "ordinal", "ORDINAL_POSITION", "ordinal_position", default=index)
        )
        data_type = str(_get_first(row, "dataType", "DATA_TYPE", "data_type", default="string"))
        nullable = bool(_get_first(row, "isNullable", "IS_NULLABLE", "is_nullable", default=True))
        attributes.append(
            {
                "ordinalNumber": ordinal,
                "name": name,
                "attributeType": "Generic String",
                "dataType": {
                    "type": data_type,
                    "nullable": nullable,
                },
                "dateAdded": now,
            }
        )
        mapping.append({"sourceName": name, "targetName": name})

    if not attributes:
        raise ValueError(f"No metadata fields returned for {data_source}:{schema or ''}.{table}")

    source["mapping"] = mapping
    content: dict[str, Any] = {
        "displayName": display_name,
        "description": description,
        "attributes": attributes,
        "sources": [source],
        "transformations": [],
        "relationships": [],
    }
    return {k: v for k, v in content.items() if v is not None}


def _build_internal_import_content(
    *,
    target_locator: str,
    source_entity: model_types.ModelEntity,
    display_name: str | None,
    description: str | None,
) -> dict[str, Any]:
    target_name = model.Locator.from_path(target_locator).entityName
    copied = source_entity.model_dump(exclude={"id", "name"})
    copied["attributes"] = [attr.model_dump(exclude_none=True) for attr in source_entity.attributes]
    copied["sources"] = [{"sourceLocation": source_entity.id}]
    copied["relationships"] = []
    copied["transformations"] = []
    copied["displayName"] = display_name or target_name or source_entity.displayName
    copied["description"] = description if description is not None else source_entity.description
    return copied


def _get_function_root(locator: model.Locator | str) -> Path:
    loc = model.Locator.from_path(locator) if isinstance(locator, str) else locator

    if loc.entityType != b.EntityType.MODEL_ENTITIES.value or not loc.entityName:
        raise ValueError("Function root is only available for model entity locators.")

    base_path = factory.get_model().get_base_path_for_entity_type(b.EntityType.MODEL_ENTITIES)
    return Path(base_path, *loc.folders, loc.entityName)


def _move_function_directory_if_present(from_locator: str, to_locator: str) -> None:
    from_loc = model.Locator.from_path(from_locator)
    to_loc = model.Locator.from_path(to_locator)

    if (
        from_loc.entityType != b.EntityType.MODEL_ENTITIES.value
        or to_loc.entityType != b.EntityType.MODEL_ENTITIES.value
        or not from_loc.entityName
    ):
        return

    target_name = to_loc.entityName or from_loc.entityName
    from_dir = _get_function_root(from_loc)
    to_dir = Path(
        factory.get_model().get_base_path_for_entity_type(b.EntityType.MODEL_ENTITIES),
        *to_loc.folders,
        target_name,
    )

    if from_dir == to_dir or not from_dir.exists():
        return

    to_dir.parent.mkdir(parents=True, exist_ok=True)

    if to_dir.exists():
        raise FileExistsError(f"Target function directory already exists: {to_dir}")

    from_dir.rename(to_dir)


@app.command()
def create(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    set_options: SetOption = None,
    body_path: BodyOption = None,
    json_body: JsonBodyOption = None,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Create an entity by locator."""
    operation = "create"
    try:
        body = _parse_body(set_options=set_options, body_path=body_path, json_body=json_body)
        model_ = _load_model_for_cli(solution_path, log_level, version)
        if model_.has_locator(locator):
            _fail(
                f"Entity already exists: {locator}",
                json_output=json_output,
                operation=operation,
                locator=locator,
                code="ENTITY_EXISTS",
            )
        model_.add_entity(locator, _create_content(locator, body))
        model_.save(locator)
    except typer.Exit:
        raise
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=locator)

    _emit_success(
        {"status": "ok", "operation": operation, "locator": locator, "changed": True},
        json_output=json_output,
        message=f"Created entity at {locator}",
    )


@app.command()
def patch(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    set_options: SetOption = None,
    body_path: BodyOption = None,
    json_body: JsonBodyOption = None,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Patch an entity by applying top-level fields."""
    operation = "patch"
    try:
        body = _parse_body(set_options=set_options, body_path=body_path, json_body=json_body)
        model_ = _load_model_for_cli(solution_path, log_level, version)
        wrapper = model_.get_entity_by_locator(locator)
        wrapper.update(**body)
        model_.save(locator)
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=locator)

    _emit_success(
        {"status": "ok", "operation": operation, "locator": locator, "changed": True},
        json_output=json_output,
        message=f"Patched entity at {locator}",
    )


@app.command()
def delete(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    yes: YesOption = False,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Delete an entity or locator subtree after confirmation."""
    operation = "delete"
    deleted: list[str] = []
    try:
        model_ = _load_model_for_cli(solution_path, log_level, version)
        affected = model_.get_entities_for_locator(locator)
        if len(affected) == 0:
            _fail(
                f"Entity not found: {locator}",
                json_output=json_output,
                operation=operation,
                locator=locator,
                code="ENTITY_NOT_FOUND",
            )
        if not yes:
            locators = "\n".join(str(wrapper.locator) for wrapper in affected)
            typer.echo(f"Delete scope:\n{locators}", err=True)
            if not typer.confirm("Delete these entities?"):
                raise typer.Exit(1)
        deleted = [str(loc) for loc in model_.delete_entities(locator)]
        model_.save(locator)
    except typer.Exit:
        raise
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=locator)

    _emit_success(
        {
            "status": "ok",
            "operation": operation,
            "locator": locator,
            "deleted": deleted,
            "changed": True,
        },
        json_output=json_output,
        message=f"Deleted {len(deleted)} entity/entities under {locator}",
    )


@app.command()
def clone(
    locator: opts.Locator,
    new_locator: Annotated[str, typer.Argument(help="New entity locator")],
    solution_path: opts.SolutionPath,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Clone an entity to a new locator."""
    operation = "clone"
    try:
        model_ = _load_model_for_cli(solution_path, log_level, version)
        if model_.has_locator(new_locator):
            _fail(
                f"Entity already exists: {new_locator}",
                json_output=json_output,
                operation=operation,
                locator=locator,
                code="ENTITY_EXISTS",
            )
        model_.clone_entity(locator, new_locator)
        model_.save(new_locator)
    except typer.Exit:
        raise
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=locator)

    _emit_success(
        {
            "status": "ok",
            "operation": operation,
            "locator": locator,
            "new_locator": new_locator,
            "changed": True,
        },
        json_output=json_output,
        message=f"Cloned {locator} to {new_locator}",
    )


@app.command()
def move(
    from_locator: Annotated[str, typer.Argument(help="Source locator")],
    to_locator: Annotated[str, typer.Argument(help="Target locator")],
    solution_path: opts.SolutionPath,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Move an entity or locator subtree."""
    operation = "move"
    moved: list[model.EntityWrapperVariant] = []
    try:
        model_ = _load_model_for_cli(solution_path, log_level, version)
        moved = model_.move_entities(from_locator, to_locator)
        _move_function_directory_if_present(from_locator, to_locator)
        model_.save()
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=from_locator)

    _emit_success(
        {
            "status": "ok",
            "operation": operation,
            "from_locator": from_locator,
            "to_locator": to_locator,
            "changed": len(moved) > 0,
        },
        json_output=json_output,
        message=f"Moved {from_locator} to {to_locator}",
    )


@app.command()
def show(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    json_output: opts.JsonOutput = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Show an entity by locator."""
    model_ = _load_model_for_cli(solution_path, log_level, version)
    wrapper = model_.get_entity_by_locator(locator)
    utils.emit_result(wrapper.entity, models=[wrapper.entity], json=json_output, pretty=True)


@app.command("list")
def list_entities(
    solution_path: opts.SolutionPath,
    locator: opts.Locator = "modelEntities",
    json_output: opts.JsonOutput = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """List entities below a locator."""
    model_ = _load_model_for_cli(solution_path, log_level, version)
    wrappers = model_.get_entities(locator)
    utils.emit_result(
        f"{len(wrappers)} entities in total",
        *[str(wrapper.locator) for wrapper in wrappers],
        models=[wrapper.entity for wrapper in wrappers],
        json=json_output,
    )


@import_app.command("external")
def import_external(
    target_locator: Annotated[str, typer.Argument(help="Target model entity locator")],
    data_source: Annotated[str, typer.Option("--data-source", help="Data source name")],
    table: Annotated[str, typer.Option("--table", help="Source table name")],
    solution_path: opts.SolutionPath,
    schema: Annotated[str | None, typer.Option("--schema", help="Source schema name")] = None,
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    source_alias: Annotated[str | None, typer.Option("--source-alias")] = None,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Import one external source table as a model entity."""
    operation = "import-external"
    try:
        model_ = _load_model_for_cli(solution_path, log_level, version)
        if model_.has_locator(target_locator):
            _fail(
                f"Entity already exists: {target_locator}",
                json_output=json_output,
                operation=operation,
                locator=target_locator,
                code="ENTITY_EXISTS",
            )
        plugin = factory.get_plugin_for_data_source(data_source)
        metadata = plugin.get_table_metadata(table, schema)
        content = _build_external_import_content(
            data_source=data_source,
            schema=schema,
            table=table,
            metadata=metadata,
            display_name=display_name,
            description=description,
            source_alias=source_alias,
        )
        model_.add_entity(target_locator, content)
        model_.save(target_locator)
    except typer.Exit:
        raise
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=target_locator)

    _emit_success(
        {
            "status": "ok",
            "operation": operation,
            "locator": target_locator,
            "data_source": data_source,
            "schema": schema,
            "table": table,
            "changed": True,
        },
        json_output=json_output,
        message=f"Imported {data_source}:{schema + '.' if schema else ''}{table} to {target_locator}",
    )


@import_app.command("internal")
def import_internal(
    target_locator: Annotated[str, typer.Argument(help="Target model entity locator")],
    source_locator: Annotated[
        str, typer.Option("--source-locator", help="Source model entity locator")
    ],
    solution_path: opts.SolutionPath,
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    json_output: JsonOutputOption = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """Import one model entity from another model entity as an internal source."""
    operation = "import-internal"
    try:
        model_ = _load_model_for_cli(solution_path, log_level, version)
        if model_.has_locator(target_locator):
            _fail(
                f"Entity already exists: {target_locator}",
                json_output=json_output,
                operation=operation,
                locator=target_locator,
                code="ENTITY_EXISTS",
            )
        wrapper = model_.get_entity_by_locator(source_locator)
        if not isinstance(wrapper.entity, model_types.ModelEntity):
            _fail(
                f"Source is not a model entity: {source_locator}",
                json_output=json_output,
                operation=operation,
                locator=target_locator,
                code="INVALID_SOURCE_TYPE",
            )
        source_entity = cast(model_types.ModelEntity, wrapper.entity)
        content = _build_internal_import_content(
            target_locator=target_locator,
            source_entity=source_entity,
            display_name=display_name,
            description=description,
        )
        model_.add_entity(target_locator, content)
        model_.save(target_locator)
    except typer.Exit:
        raise
    except Exception as err:
        _fail(str(err), json_output=json_output, operation=operation, locator=target_locator)

    _emit_success(
        {
            "status": "ok",
            "operation": operation,
            "locator": target_locator,
            "source_locator": source_locator,
            "changed": True,
        },
        json_output=json_output,
        message=f"Imported {source_locator} internally to {target_locator}",
    )
