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

import sys
from pathlib import Path

import rich
import typer

from .. import factory, opts, utils

app = typer.Typer(
    name="validate",
    add_completion=False,
    no_args_is_help=False,
    help="Validate solution model.",
)

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.callback(invoke_without_command=True)
def command(
    solution_path: Path | None = typer.Option(
        None,
        "--solution",
        "-s",
        "--solution-path",
        help="Path to .dm8s solution file (or folder containing exactly one .dm8s file).",
        envvar="DATAM8_SOLUTION_PATH",
    ),
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        "-l",
        help="Set log level (defaults to global --log-level or DATAM8_LOG_LEVEL).",
        envvar="DATAM8_LOG_LEVEL",
    ),
):
    """Validate solution model."""
    if solution_path is None:
        raise typer.BadParameter("No solution specified. Use --solution/-s (or set DATAM8_SOLUTION_PATH).")

    effective_log_level = log_level
    if not isinstance(effective_log_level, str) or not effective_log_level.strip():
        effective_log_level = opts.LogLevels.WARNING.value

    try:
        _ = factory.validate_solution_model(
            solution_path=solution_path,
            log_level=effective_log_level,
        )
    except Exception as err:
        logger.error(err)
        sys.exit(1)

    rich.print("Validation successfull")
