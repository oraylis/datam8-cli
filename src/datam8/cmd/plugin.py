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

"""Plugin discovery for people and agent clients."""

from typing import Annotated

import rich
import typer

from datam8 import config, opts, parser
from datam8.plugins import PluginManager, init_builtin_plugins

from . import common

app = typer.Typer(
    name="plugins",
    help="Inspect plugin manifests and connection configuration",
    no_args_is_help=True,
)
PluginId = Annotated[str, typer.Argument(help="Plugin ID, e.g. builtin:SQLServer")]


def plugin_class(plugin_id, solution_path, log_level, version):
    common.main_callback(solution_path, log_level, version)
    init_builtin_plugins(plugin_id=plugin_id)
    manager = PluginManager(parser.parse_solution_file(config.solution_path))
    return manager.get_plugin_manifest(plugin_id), manager.get_plugin(plugin_id)


@app.command()
@common.output
def list(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    common.main_callback(solution_path, log_level, version)
    solution = parser.parse_solution_file(config.solution_path)
    init_builtin_plugins()
    items = PluginManager(solution).get_plugins()
    if not json_output:
        for plugin in items:
            rich.print(plugin)
    return {"count": len(items), "items": items}


@app.command()
@common.output
def show(
    plugin_id: PluginId,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    manifest, plugin = plugin_class(plugin_id, solution_path, log_level, version)
    connections = plugin.get_connection_properties()
    mappings = plugin.get_data_type_mappings()
    if not json_output:
        rich.print(manifest)
        typer.echo("Connection Properties")
        rich.print(connections)
        typer.echo("DataType mappings")
        rich.print(mappings)
    return {
        "item": {
            "manifest": manifest,
            "connectionProperties": connections,
            "dataTypeMappings": mappings,
        }
    }


@app.command("ui-schema")
@common.output
def ui_schema(
    plugin_id: PluginId,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _, plugin = plugin_class(plugin_id, solution_path, log_level, version)
    result = plugin.get_ui_schema()
    if not json_output:
        rich.print(result)
    return {"item": result}


@app.command("connection-properties")
@common.output
def connection_properties(
    plugin_id: PluginId,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _, plugin = plugin_class(plugin_id, solution_path, log_level, version)
    items = plugin.get_connection_properties()
    if not json_output:
        rich.print(items)
    return {"count": len(items), "items": items}


@app.command("data-type-mappings")
@common.output
def data_type_mappings(
    plugin_id: PluginId,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _, plugin = plugin_class(plugin_id, solution_path, log_level, version)
    items = plugin.get_data_type_mappings()
    if not json_output:
        rich.print(items)
    return {"count": len(items), "items": items}
