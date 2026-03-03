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

import rich
import typer

from datam8 import config, factory, opts

from . import common

app = typer.Typer(
    name="validate",
    add_completion=False,
    no_args_is_help=False,
    help="Validate solution model.",
)


@app.callback(invoke_without_command=True)
def main(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Validate solution model."""
    common.main_callback(solution_path, log_level, version)

    factory.create_model_or_exit(
        solution_path=config.solution_path,
    )

    rich.print("Validation successfull")
