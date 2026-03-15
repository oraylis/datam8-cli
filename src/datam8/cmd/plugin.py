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
from typing import Annotated

import rich
import typer

from datam8 import config, logging, opts, parser
from datam8.plugins import PluginManager

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="plugins",
    help="Subcommands to manage plugins",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)


@app.command()
def list(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available plugins"
    common.main_callback(solution_path, log_level, version)

    solution = parser.parse_solution_file(config.solution_path)
    pm = PluginManager(solution)

    for plugin in pm.get_plugins():
        rich.print(plugin)


@app.command()
def show(
    name: Annotated[str, typer.Argument(help="Plugin name")],
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available plugins"
    common.main_callback(solution_path, log_level, version)

    solution = parser.parse_solution_file(config.solution_path)
    pm = PluginManager(solution)
    plugin = pm.get_plugin_manifest(name)

    rich.print(plugin)


@app.command()
def list_schemas(
    name: Annotated[str, typer.Argument(help="Datasource name")],
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available plugins"
    common.main_callback(solution_path, log_level, version)

    from datam8 import factory

    model = factory.create_model_or_exit()
    data_source = model.get_data_source(name)
    plugin = factory.get_plugin_for_data_source(data_source.entity)

    rich.print(plugin.list_schemas())
