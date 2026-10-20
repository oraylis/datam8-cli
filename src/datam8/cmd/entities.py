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

"""Entity commands and machine-readable local batches."""

from typing import Annotated

import typer

from datam8 import opts
from datam8.operations import Batch, Operation, schema_for

from . import common

app = typer.Typer()
Data = Annotated[str | None, typer.Option(help="JSON input, alternatively use --file")]
File = Annotated[str | None, typer.Option(help="UTF-8 JSON input file; - reads stdin")]
At = Annotated[str | None, typer.Option(help='JSON path, e.g. ["attributes",{"name":"Id"}]')]
Fields = Annotated[str | None, typer.Option(help="Comma-separated entity fields to include")]


@app.command("list")
@common.output
def list_(
    solution_path: opts.SolutionPath,
    locator: opts.Locator = "modelEntities",
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
    fields: Fields = None,
    limit: Annotated[int | None, typer.Option(min=0)] = None,
    offset: Annotated[int, typer.Option(min=0)] = 0,
):
    """List compact entity summaries, optionally including selected fields."""
    session = common.session(solution_path, log_level, version)
    result = session.list(
        locator, fields, (100 if json_output else 0) if limit is None else limit, offset
    )
    if not json_output:
        typer.echo(f"{result['count']} entities in total")
        for item in result["items"]:
            typer.echo(item["locator"])
    return result


@app.command()
@common.output
def list_by_property(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    model_locator: opts.LocatorOpt = "modelEntities",
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
    fields: Fields = None,
):
    """List entities with a specific property assignment."""
    result = common.session(solution_path, log_level, version).list(
        model_locator, fields, limit=0, property_locator=locator
    )
    if not json_output:
        typer.echo(f"{result['count']} entities in total")
        for item in result["items"]:
            typer.echo(item["locator"])
    return result


@app.command()
@common.output
def show(
    selector: opts.Selector,
    solution_path: opts.SolutionPath,
    by: opts.SelectBy = opts.Selectors.LOCATOR,
    json_output: opts.JsonOutput = False,
    version: opts.Version = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    at: At = None,
    fields: Fields = None,
):
    """Read one entity or a keyed nested value."""
    session = common.session(solution_path, log_level, version)
    result = session.show(selector, by.value, common.input_path(at), fields)
    if not json_output:
        import rich

        wrapper = session.model.get_entity_by_selector(selector, by=by)
        typer.echo(f"File: {wrapper.source_file}")
        typer.echo("\nProperties:")
        for value in wrapper.properties.values():
            rich.print(value)
        typer.echo("\nRaw Data:")
        rich.print(result["item"]["data"])
    return result


def mutate(operation, solution_path, log_level, version, json_output):
    result = common.session(solution_path, log_level, version).execute(operation)
    if not json_output:
        typer.echo(f"{operation.op}: {operation.locator}")
    return result


@app.command()
@common.output
def create(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    data: Data = None,
    file: File = None,
    at: At = None,
    source_file: Annotated[str | None, typer.Option()] = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Create an entity or append a nested list entry."""
    args = {"op": "create", "locator": locator, "data": common.input_value(data, file)}
    if at is not None:
        args["at"] = common.input_path(at)
    if source_file is not None:
        args["sourceFile"] = source_file
    return mutate(Operation.model_validate(args), solution_path, log_level, version, json_output)


@app.command()
@common.output
def update(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    data: Data = None,
    file: File = None,
    at: At = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Update selected fields without replacing the complete entity."""
    return mutate(
        Operation(
            op="update",
            locator=locator,
            data=common.input_value(data, file),
            at=common.input_path(at),
        ),
        solution_path,
        log_level,
        version,
        json_output,
    )


@app.command()
@common.output
def delete(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    at: At = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Delete entities or a selected nested field/item."""
    return mutate(
        Operation(op="delete", locator=locator, at=common.input_path(at)),
        solution_path,
        log_level,
        version,
        json_output,
    )


@app.command()
@common.output
def clone(
    locator: opts.Locator,
    new_locator: str,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Clone an entity to a new locator."""
    return mutate(
        Operation(op="clone", locator=locator, new_locator=new_locator),
        solution_path,
        log_level,
        version,
        json_output,
    )


@app.command()
@common.output
def rename(
    solution_path: opts.SolutionPath,
    locator: opts.Locator,
    new_name: str,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Rename an entity using existing reference handling."""
    result = mutate(
        Operation(op="rename", locator=locator, new_name=new_name),
        solution_path,
        log_level,
        version,
        True,
    )
    if not json_output:
        typer.echo(f"Renamed '{locator}' to '{new_name}'")
    return result


@app.command()
@common.output
def move(
    solution_path: opts.SolutionPath,
    src: opts.Locator,
    dst: opts.Locator,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    force: bool = False,
    json_output: opts.JsonOutput = False,
):
    """Move entities or complete folder subtrees."""
    result = mutate(
        Operation(op="move", locator=src, new_locator=dst, force=force),
        solution_path,
        log_level,
        version,
        True,
    )
    if not json_output:
        typer.echo(
            "The following entities were moved:" if result["changed"] else "No entities were moved"
        )
        for locator in result["changed"]:
            typer.echo(f" - {locator}")
    return result


@app.command()
@common.output
def schema(entity_type: str, at: At = None, json_output: opts.JsonOutput = False):
    """Read the existing schema for an entity type or nested field."""
    result = {"item": schema_for(entity_type, common.input_path(at))}
    if not json_output:
        import rich

        rich.print(result["item"])
    return result


@app.command()
@common.output
def apply(
    solution_path: opts.SolutionPath,
    file: str = typer.Option(..., help="Batch JSON file; - reads stdin"),
    json_output: opts.JsonOutput = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Apply an ordered JSON batch, stopping after the first failure."""
    batch = Batch.model_validate(common.input_value(file=file))
    session = common.session(solution_path, log_level, version)
    results = []
    for index, operation in enumerate(batch.operations):
        try:
            result = session.execute(operation)
            results.append({"index": index, "op": operation.op, **result})
        except Exception as exc:
            error, code = common.command_error(exc)
            if not json_output:
                typer.echo(f"Stopped at operation {index}: {error['message']}", err=True)
            return {
                "ok": False,
                "results": results,
                "failedIndex": index,
                "error": error,
                "_exit_code": code,
            }
    if not json_output:
        typer.echo(f"Completed {len(results)} operations")
    return {"results": results}


@app.command()
@common.output
def validate(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Validate the persisted solution model."""
    session = common.session(solution_path, log_level, version)
    session.model.resolve()
    if not json_output:
        typer.echo("Validation successful")
    return {"item": {"valid": True}}


@app.command("generate")
@common.output
def generate_cmd(
    solution_path: opts.SolutionPath,
    target: opts.GeneratorTarget = opts.default_target,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    clean_output: opts.CleanOutput = False,
    payloads: opts.Payload = [],
    generate_all: opts.AllTargets = False,
    lazy: opts.Lazy = False,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Generate the selected target from the persisted solution."""
    session = common.session(solution_path, log_level, version)
    if generate_all:
        typer.echo("The --all option is set, but is currently ignored.", err=True)
    result = session.execute(
        Operation(
            op="generate",
            target=None if target == opts.default_target else target,
            payloads=payloads,
            clean_output=clean_output,
            lazy=lazy,
        )
    )
    if not json_output:
        typer.echo("Generation successful")
    return result
