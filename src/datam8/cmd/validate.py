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

import os
import sys
from pathlib import Path

import rich
import typer

from .. import config, factory, opts, utils

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.command("validate")
def command(
    ctx: typer.Context,
    solution_path: Path | None = typer.Option(
        None,
        "--solution",
        "-s",
        "--solution-path",
        help="Path to .dm8s solution file (or folder containing exactly one .dm8s file).",
        envvar="DATAM8_SOLUTION_PATH",
    ),
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
):
    """Validate solution model."""
    if solution_path is None:
        parent_obj = getattr(ctx, "obj", None)
        candidate = getattr(parent_obj, "solution", None) if parent_obj is not None else None
        if not isinstance(candidate, str) or not candidate.strip():
            candidate = os.environ.get("DATAM8_SOLUTION_PATH")
        if not isinstance(candidate, str) or not candidate.strip():
            raise typer.BadParameter("No solution specified. Use --solution/-s (or set DATAM8_SOLUTION_PATH).")
        solution_path = Path(candidate)

    config.log_level = log_level
    config.lazy = False
    config.solution_path = solution_path
    config.solution_folder_path = solution_path.parent.absolute()

    _ = factory.create_model()

    rich.print("Validation successfull")
