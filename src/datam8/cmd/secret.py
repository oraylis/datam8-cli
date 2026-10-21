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

from pathlib import Path, PurePosixPath
from typing import Annotated

import typer

from datam8 import config, logging, opts
from datam8.secrets import SecretResolver

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="secrets",
    help="Subcommands to manage secrets",
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

    secrets = SecretResolver().list_secrets()

    typer.echo(f"{len(secrets)} Secrets found for solution {config.get_name()}")
    for i in range(len(secrets)):
        typer.echo(f"- {i + 1}: {secrets[i]}")


@app.command()
def add(
    path: Annotated[Path, typer.Argument(help="Path to store the secret in the keyring backend")],
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Add a new secret"
    common.main_callback(solution_path, log_level, version)

    secret = typer.prompt("New Secret Value", hide_input=True)
    SecretResolver().set_secret(PurePosixPath(path), secret)


@app.command()
def unset(
    path: opts.SecretPath,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Remove a secret"
    common.main_callback(solution_path, log_level, version)
    SecretResolver().unset_secret(PurePosixPath(path))
    typer.echo(f"Successfully uset {path}")


@app.command()
def clean(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Clean all secrets for this solution, effectly deleting them"
    common.main_callback(solution_path, log_level, version)

    if typer.confirm("Are you sure you want to delete all registered secrets?"):
        SecretResolver().clean()


@app.command()
@common.output
def check(
    path: opts.SecretPath,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Check whether a secret can be resolved without revealing its value."""
    from datam8.errors import Datam8NotFoundError

    common.main_callback(solution_path, log_level, version)
    if SecretResolver().get_secret(path.as_posix()) is None:
        raise Datam8NotFoundError(message="Secret is not available")
    if not json_output:
        typer.echo("Secret is available")
    return {"item": {"path": path.as_posix(), "available": True}}


@app.command("set")
@common.output
def set_(
    path: opts.SecretPath,
    solution_path: opts.SolutionPath,
    file: Annotated[str, typer.Option(help="Secret value file; - reads stdin")],
    force: bool = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    """Set a secret without prompting or echoing the value."""
    common.main_callback(solution_path, log_level, version)
    SecretResolver().set_secret(
        path.as_posix(), common.input_value(file=file, text=True), force=force
    )
    if not json_output:
        typer.echo(f"Stored secret '{path.as_posix()}'")
    return {"path": path.as_posix(), "stored": True}
