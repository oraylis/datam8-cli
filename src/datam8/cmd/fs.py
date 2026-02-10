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

from datam8.core.workspace_io import list_directory

from .common import emit_result, get_global_options

app = typer.Typer(
    name="fs",
    add_completion=False,
    no_args_is_help=True,
    help="List files and folders.",
)


@app.command("list")
def fs_list(
    ctx: typer.Context,
    path: str | None = typer.Option(None, "--path", help="Directory path (defaults to current working directory)."),
) -> None:
    """List directory entries for a path."""
    opts = get_global_options(ctx)
    entries = list_directory(path)
    payload = {"entries": entries}
    human_lines = [f"{e['type']} {e['name']}" for e in entries]
    emit_result(opts, payload, human_lines=human_lines)
