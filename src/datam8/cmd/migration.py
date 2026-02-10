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

from typing import Any

import typer

from datam8 import opts as cli_opts
from datam8.core.migration_v1_to_v2 import migrate_solution_v1_to_v2

from .common import emit_result, make_global_options, read_json_arg

app = typer.Typer(
    name="migration",
    add_completion=False,
    no_args_is_help=True,
    help="Migrate v1 solutions to v2 layout.",
)


@app.command("v1-to-v2")
def v1_to_v2(
    source_solution_path: str = typer.Option(..., "--source-solution-path"),
    target_dir: str = typer.Option(..., "--target-dir"),
    options: str = typer.Option("{}", "--options", help="JSON object with migration options."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Migrate a v1 solution into a v2-compatible project."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    parsed_options = read_json_arg(options)
    args: dict[str, Any] = {
        "sourceSolutionPath": source_solution_path,
        "targetDir": target_dir,
    }
    if isinstance(parsed_options, dict):
        args["options"] = parsed_options
    result = migrate_solution_v1_to_v2(args)
    emit_result(opts, result)
