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

import rich
import typer

from datam8 import config, logging, opts, solution

from . import common

app = typer.Typer(
    name="init",
    add_completion=False,
    no_args_is_help=False,
)

logger = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def main(
    name: opts.SolutionName,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
):
    """Initialise a new DataM8 solution"""
    common.version_callback(version)
    config.log_level = log_level
    logging.setup_logger()

    new_solution_path = solution_path.resolve()
    if solution_path.suffix != ".dm8s":
        new_solution_path = new_solution_path / f"{name}.dm8s"

    if new_solution_path.exists():
        logger.error("Solution file aready exists at %s", new_solution_path)
        sys.exit(1)

    solution.init_solution(new_solution_path)

    rich.print("Initialisation successfull")
