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

import asyncio
import os
import sys
from pathlib import Path

import rich
import typer

from datam8.core.validation import validate_solution_dm8s

from .. import config, opts, utils

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
        help="Path to a .dm8s solution file.",
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

    if solution_path.suffix.lower() != ".dm8s":
        raise typer.BadParameter("Validation expects a .dm8s solution file path.")

    config.log_level = log_level
    report = asyncio.run(validate_solution_dm8s(solution_path))

    if report["ok"]:
        summary = report["summary"]
        rich.print("Validation OK")
        rich.print(
            f"Entities parsed: {summary['entitiesParsed']} "
            f"(model: {summary['modelEntitiesParsed']}, base: {summary['baseEntitiesParsed']})"
        )
        return

    rich.print("Validation failed")
    for err in report["errors"]:
        line = f"- [{err.get('code', 'UNKNOWN_ERROR')}] {err.get('message', 'Unknown error')}"
        if err.get("path"):
            line += f" ({err['path']})"
        if err.get("entityLocator"):
            line += f" [{err['entityLocator']}]"
        rich.print(line)

    raise typer.Exit(code=1)
