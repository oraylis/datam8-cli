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

import typer

from datam8 import factory, logging, opts

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="sources",
    help="Subcommands to connect with and view sources",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)


@app.command()
def list_tables(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    schema_name: opts.SchemaName = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available source tables"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    tables = plugin.list_tables(schema_name)

    typer.echo(f"Found {len(tables)} tables")
    for tab in tables:
        typer.echo(tab)


@app.command()
def preview(
    data_source_name: opts.DataSource,
    table_name: opts.TableName,
    solution_path: opts.SolutionPath,
    limit: opts.Limit = 10,
    schema_name: opts.SchemaName = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available plugins"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    try:
        preview = plugin.preview_data(table_name, schema_name, limit=limit)
    except Exception as err:
        typer.echo("Error previewing data")
        typer.echo(err)
        raise typer.Exit(1)

    typer.echo(f"Showing first {len(preview)} entries")
    for entry in preview:
        typer.echo(entry)


@app.command()
def test_connection(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Validate connectionstring and try connecting to the source"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    try:
        plugin.validate_connection()
        plugin.test_connection()
    except Exception as err:
        typer.echo("Connection could not be established")
        typer.echo(err)
        raise typer.Exit(1) from err

    typer.echo("Datasource tested successfully")
