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

"""Inspect the solution descriptor without dumping the metadata model."""

import typer

from datam8 import config, opts, parser

from . import common
from .entities import Fields

app = typer.Typer(name="solution", help="Read the solution descriptor", no_args_is_help=True)


@app.command()
@common.output
def show(
    solution_path: opts.SolutionPath,
    fields: Fields = None,
    json_output: opts.JsonOutput = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Read solution paths and generator targets; optionally select fields."""
    common.main_callback(solution_path, log_level, version)
    data = parser.parse_solution_file(config.solution_path).model_dump(
        mode="json", exclude_unset=True
    )
    if fields:
        data = {field: data[field] for field in fields.split(",") if field in data}
    if not json_output:
        import rich

        rich.print(data)
    return {"item": data}
