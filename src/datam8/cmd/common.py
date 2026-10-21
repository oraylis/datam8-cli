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

import functools
import json
import sys
from collections.abc import Sequence
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from typing import Any

import click
import typer
from pydantic import ValidationError
from pydantic_core import to_json
from typer.core import TyperGroup

from datam8 import config, errors, logging, opts, utils

logger = logging.getLogger(__name__)


def emit_json(value):
    typer.echo(to_json(value, fallback=str).decode("utf-8"))


def command_error(exc):
    if isinstance(exc, errors.Datam8Error):
        return exc.to_envelope().model_dump(exclude_none=True), exc.exit_code if exc.exit_code in (
            2,
            3,
        ) else 1
    if isinstance(exc, (FileNotFoundError, KeyError, errors.EntityNotFoundError)):
        return {"code": "not_found", "message": str(exc)}, 3
    if isinstance(
        exc,
        (
            ValueError,
            AssertionError,
            ValidationError,
            click.ClickException,
            errors.InvalidLocatorError,
            errors.ModelParseError,
            errors.NotSupportedModelVersionError,
            FileExistsError,
        ),
    ):
        details = (
            exc.errors(include_input=False, include_url=False)
            if isinstance(exc, ValidationError)
            else None
        )
        error = {
            "code": "validation_error",
            "message": str(exc) if not details else "Invalid command data",
        }
        if details:
            error["details"] = details
        return error, 2
    return {"code": "execution_error", "message": str(exc)}, 1


def output(function):
    """Keep machine stdout separate from library/plugin output and normalize failures."""

    @functools.wraps(function)
    def invoke(*args, **kwargs):
        machine = kwargs.get("json_output", False)
        token = utils.capture_cli_errors.set(True)
        try:
            with redirect_stdout(sys.stderr) if machine else nullcontext():
                result = function(*args, **kwargs)
        except click.exceptions.Exit as exc:
            if exc.exit_code == 0:
                raise
            if machine:
                emit_json(
                    {
                        "ok": False,
                        "error": {
                            "code": "execution_error",
                            "message": "Command failed; see stderr",
                        },
                    }
                )
            raise
        except Exception as exc:
            error, code = command_error(exc)
            if machine:
                emit_json({"ok": False, "error": error})
            else:
                typer.echo(error["message"], err=True)
            raise typer.Exit(code) from None
        finally:
            utils.capture_cli_errors.reset(token)
        exit_code = result.pop("_exit_code", 0) if isinstance(result, dict) else 0
        if machine:
            emit_json({"ok": True, **(result or {})})
        if exit_code:
            raise typer.Exit(exit_code)
        return result

    # Typer evaluates annotations on this wrapper, including postponed annotations.
    from typing import get_type_hints

    invoke.__annotations__ = get_type_hints(function, include_extras=True)
    return invoke


class CliGroup(TyperGroup):
    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        arguments = list(sys.argv[1:] if args is None else args)
        if "--json" in arguments:
            for stream in (sys.stdout, sys.stderr):
                reconfigure = getattr(stream, "reconfigure", None)
                if callable(reconfigure):
                    reconfigure(encoding="utf-8")
        standalone = standalone_mode
        try:
            result = super().main(
                args=arguments,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except click.ClickException as exc:
            if "--json" in arguments:
                error, code = command_error(exc)
                emit_json({"ok": False, "error": error})
            else:
                exc.show()
                code = exc.exit_code
            if standalone:
                raise SystemExit(code) from None
            raise
        if standalone:
            raise SystemExit(result if isinstance(result, int) else 0)
        return result


def input_value(data: str | None = None, file: str | None = None, *, text=False):
    if (data is None) == (file is None):
        raise errors.Datam8ValidationError(
            message="Provide exactly one of --data or --file (use - for stdin)"
        )
    if data is not None:
        value = data
    elif file == "-":
        reconfigure = getattr(sys.stdin, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8-sig")
        value = sys.stdin.read()
    else:
        assert file is not None
        value = Path(file).read_text(encoding="utf-8-sig")
    return value if text else json.loads(value)


def input_path(value):
    if value is None:
        return None
    at = json.loads(value)
    if not isinstance(at, list):
        raise errors.Datam8ValidationError(message="--at must be a JSON array")
    # Reuse the operation path validation for reads as well.
    from datam8.operations import Operation

    return Operation(op="delete", locator="/", at=at).at


def session(solution_path, log_level, version=False):
    from datam8.operations import ModelSession

    main_callback(solution_path, log_level, version)
    return ModelSession(config.solution_path)


def main_callback(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
) -> None:
    """CLI root callback."""
    version_callback(version)

    context = click.get_current_context(silent=True)
    if context is not None and context.parent is not None:
        root = context.find_root()
        if context.get_parameter_source("solution_path") in (
            click.core.ParameterSource.DEFAULT,
            click.core.ParameterSource.ENVIRONMENT,
        ):
            if root.get_parameter_source("solution_path") in (
                click.core.ParameterSource.COMMANDLINE,
                click.core.ParameterSource.ENVIRONMENT,
            ):
                solution_path = root.params["solution_path"]

    try:
        config.set_solution(solution_path)
    except errors.Datam8Error as err:
        if utils.capture_cli_errors.get():
            raise
        typer.echo(err.message)
        raise typer.Exit(1)

    config.log_level = log_level

    logging.setup_logger()


def version_callback(value: bool) -> None:
    """Print CLI version when --version is passed."""
    if value:
        typer.echo(config.get_version())
        raise typer.Exit(code=0)
