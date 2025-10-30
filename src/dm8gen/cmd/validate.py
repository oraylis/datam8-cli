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

from .. import config, factory, opts, utils

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.command("validate")
def command(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
):
    """Validate solution model."""
    config.log_level = log_level
    config.lazy = False
    config.solution_path = solution_path
    config.solution_folder_path = solution_path.parent.absolute()

    _ = factory.create_model()

    rich.print("Validation successfull")
