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

import typer

from datam8 import opts as cli_opts
from datam8.core.workspace_io import list_directory

from .common import emit_result, make_global_options

app = typer.Typer(
    name="fs",
    add_completion=False,
    no_args_is_help=True,
    help="List files and folders.",
)


@app.command("list")
def fs_list(
    path: str | None = typer.Option(None, "--path", help="Directory path (defaults to current working directory)."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List directory entries for a path."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    entries = list_directory(path)
    payload = {"entries": [entry.model_dump() for entry in entries]}
    human_lines = [f"{entry.type} {entry.name}" for entry in entries]
    emit_result(opts, payload, human_lines=human_lines)
