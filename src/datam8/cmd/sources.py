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

"""Source discovery, import and refresh through the same model operations as HTTP."""

from typing import Annotated, Literal

import typer

from datam8 import errors, opts
from datam8.operations import Operation

from . import common

app = typer.Typer(
    name="sources", help="Inspect sources, import and refresh model entities", no_args_is_help=True
)
Mode = Annotated[Literal["complete", "sources-only"], typer.Option()]


def read_source(
    action, data_source, location, solution_path, log_level, version, json_output, limit=10
):
    result = common.session(solution_path, log_level, version).source_info(
        action, data_source, location, limit
    )
    if not json_output:
        if action == "test-connection":
            typer.echo("Datasource tested successfully")
        elif "items" in result:
            import polars as pl

            if action == "list":
                typer.echo(f"Found {result['count']} source objects")
            if result["items"]:
                pl.DataFrame(result["items"]).show(limit=None, tbl_hide_dataframe_shape=True)
        else:
            import rich

            rich.print(result.get("item"))
    return result


@app.command("list")
@common.output
def list_(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    source_location: opts.SourceLocation | None = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "list", data_source_name, source_location, solution_path, log_level, version, json_output
    )


@app.command()
@common.output
def capabilities(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "capabilities", data_source_name, None, solution_path, log_level, version, json_output
    )


@app.command()
@common.output
def preview(
    data_source_name: opts.DataSource,
    source_location: opts.SourceLocation,
    solution_path: opts.SolutionPath,
    limit: opts.Limit = 10,
    col_limit: opts.ColLimit = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "preview",
        data_source_name,
        source_location,
        solution_path,
        log_level,
        version,
        json_output,
        limit,
    )


@app.command()
@common.output
def metadata(
    data_source_name: opts.DataSource,
    source_location: opts.SourceLocation,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "metadata",
        data_source_name,
        source_location,
        solution_path,
        log_level,
        version,
        json_output,
    )


@app.command()
@common.output
def import_description(
    data_source_name: opts.DataSource,
    source_location: opts.SourceLocation,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "import-description",
        data_source_name,
        source_location,
        solution_path,
        log_level,
        version,
        json_output,
    )


@app.command()
@common.output
def test_connection(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    return read_source(
        "test-connection", data_source_name, None, solution_path, log_level, version, json_output
    )


@app.command("import")
@common.output
def import_(
    data_source: opts.DataSource,
    source_location: opts.SourceLocation,
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    result = common.session(solution_path, log_level, version).execute(
        Operation(
            op="sources.import",
            locator=locator,
            data_source=data_source,
            source_location=source_location,
        )
    )
    if not json_output:
        typer.echo(f"Source table imported into model at {locator}")
    return result


@app.command()
@common.output
def compare(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    mode: Mode = "complete",
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    result = common.session(solution_path, log_level, version).compare(locator, mode)
    if not json_output:
        import rich

        rich.print(result["item"]["diff"])
    return result


@app.command()
@common.output
def refresh(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    mode: Mode = "complete",
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    if json_output and not yes:
        raise errors.Datam8ValidationError(
            message="refresh --json requires --yes; use compare to inspect changes"
        )
    session = common.session(solution_path, log_level, version)
    if not yes:
        result = session.compare(locator, mode)
        if not result["item"]["hasChanges"]:
            typer.echo(f"No changes detected for '{locator}'")
            return result
        import rich

        rich.print(result["item"]["diff"])
        if not typer.confirm("Should these changes be imported", default=False):
            raise errors.Datam8ValidationError(message="Refresh cancelled")
    result = session.execute(Operation(op="sources.refresh", locator=locator, mode=mode))
    if not json_output:
        typer.echo("Saved detected changes")
    return result
