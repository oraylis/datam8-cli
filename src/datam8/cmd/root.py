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

"""
This module contains CLI commands to interact with the model, e.g. listing, adding or deleting
entities.

*Subcommands*
- list
- show

Not every part of datam8 is pre-imported, some parts, e.g. die api is only imported when commands  related
to those imports are executed. This reduces startup time.
"""

import json
import pathlib
from typing import Annotated

import typer

from datam8 import (
    config,
    errors,
    logging,
    opts,
)

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    cls=common.CliGroup,
    name="datam8",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_short=False,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)
"App to interact with the model - used as the default/root app"


@app.callback(invoke_without_command=True)
def _callback(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    if version:
        typer.echo(config.get_version())
        raise typer.Exit(code=0)


@app.command()
@common.output
def init(
    name: opts.SolutionName,
    solution_path: opts.SolutionPath,
    type_: Annotated[opts.SolutionTypes | None, typer.Option("--type", "-t")] = None,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """
    Initialise a new empty DataM8 solution with default base entities.
    """
    config.log_level = log_level
    common.version_callback(version)
    if type_ is None:
        type_ = (
            opts.SolutionTypes.EMPTY
            if json_output
            else opts.SolutionTypes(typer.prompt("Solution Type to initialize?", default="empty"))
        )

    new_solution_path = solution_path.resolve()
    if solution_path.suffix != ".dm8s":
        new_solution_path = new_solution_path / f"{name}.dm8s"

    if new_solution_path.exists():
        raise errors.Datam8ValidationError(
            message=f"Solution file already exists at {new_solution_path}"
        )

    if new_solution_path.parent.exists() and any(new_solution_path.parent.iterdir()):
        raise errors.Datam8ValidationError(message="Init needs to be run in an empty directory")

    from datam8 import solution

    if type_ == opts.SolutionTypes.EMPTY:
        solution.init_solution(new_solution_path)
        if not json_output:
            typer.echo(f"Blank solution created at {new_solution_path}")

    if type_ == opts.SolutionTypes.SAMPLE:
        created_version = solution.init_solution_from_sample(new_solution_path)
        if not json_output:
            typer.echo(f"Sample Solution in version {created_version} created")
    return {"item": {"solutionFile": new_solution_path.as_posix(), "type": type_.value}}


@app.command()
def serve(
    solution_path: opts.SolutionPath,
    token: opts.ApiToken = None,
    host: opts.ApiHost = "127.0.0.1",
    port: opts.ApiPort = 0,
    openapi: opts.OpenApi = False,
    export_openapi: opts.ExportOpenApi = False,
    workspace_switch: bool = False,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
):
    "Starts the DataM8 fastapi backend"
    from datam8 import factory
    from datam8.api import app as api_app  # for performance only import when needed

    config.mode = config.RunMode.API
    if workspace_switch and (host not in {"127.0.0.1", "localhost"} or not token or not token.strip()):
        raise typer.BadParameter("--workspace-switch requires a loopback host and a non-empty token")
    common.main_callback(solution_path, log_level, version)

    datam8_app = api_app.create_app(
        token=token.strip() if token is not None else token,
        enable_openapi=openapi,
        workspace_switch=workspace_switch,
    )

    if export_openapi:
        with open(pathlib.Path.cwd() / "datam8-openapi.json", "w") as f_:
            json.dump(datam8_app.openapi(), f_, indent=4)
        raise typer.Exit(0)

    _ = factory.create_model()

    sock, actual_port = api_app._bind(host, port)
    server = api_app.create_server(
        host=host,
        port=actual_port,
        app=datam8_app,
    )
    server.run(sockets=[sock])
