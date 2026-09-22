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

import typer

from datam8 import config, logging, opts

from .root import __setup_model_for_cli

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="functions",
    help="Subcommands to manage functions",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)


@app.command("list")
def list_(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List defined functions"
    from datam8.functions import get_functions

    model = __setup_model_for_cli(solution_path, log_level, version)

    for wrapper in model.modelEntities.values():
        try:
            functions = get_functions(wrapper)
        except Exception as err:
            typer.echo(wrapper.locator)
            typer.echo(str(err))
            raise typer.Exit(1)

        if len(functions) > 0:
            typer.echo(wrapper.locator)
            for f in functions:
                typer.echo(f" {f.transformation.stepNo}. {f.transformation.name}: ", nl=False)
                typer.echo(
                    f"{f.source_file_path.relative_to(config.solution_folder_path, walk_up=True)}"
                )
            typer.echo()


@app.command()
def show(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    step_no: int | None = None,
    name: str | None = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Print out the source code of a specific transformation"""
    from datam8.functions import get_function

    model = __setup_model_for_cli(solution_path, log_level, version)
    wrapper = model.modelEntities[locator]

    if step_no is None and name is None:
        typer.echo("One of step_no or name needs to be provided")
        raise typer.Exit(1)

    try:
        # -1 is just to satisfy the type checker, cannot happen due to the above if
        func = get_function(wrapper, step_no or name or -1)

        typer.echo(f"# {'=' * 78}")
        typer.echo(f"# file: {func.source_file_path.relative_to(config.solution_folder_path)}")
        typer.echo(f"# name: {func.transformation.name}")
        typer.echo(f"# stepNo: {func.transformation.stepNo}")
        typer.echo(f"# {'=' * 78}")
        typer.echo(func.source_code)
    except Exception as err:
        typer.echo(str(err))
        raise typer.Exit(1) from err


@app.command()
def move(
    locator: opts.Locator,
    new_location: opts.Path,
    solution_path: opts.SolutionPath,
    step_no: int | None = None,
    name: str | None = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Move a functions source code to a new location"""
    if step_no is None and name is None:
        typer.echo("One of step_no or name needs to be provided")
        raise typer.Exit(1)

    from datam8.functions import get_function, move_function

    model = __setup_model_for_cli(solution_path, log_level, version)
    wrapper = model.modelEntities[locator]

    try:
        func = get_function(wrapper, step_no or name)  # type: ignore[ty:invalid-argument-type]
        move_function(wrapper, func.transformation, new_location)
        model.save()
    except Exception as err:
        typer.echo(str(err))
        raise typer.Exit(1)

    typer.echo(f"Moved '{func.transformation.name}' to '{new_location}'")
