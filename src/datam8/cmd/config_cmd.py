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

import os

import typer

from .common import emit_result, get_global_options

app = typer.Typer(
    name="config",
    add_completion=False,
    no_args_is_help=True,
    help="Show effective runtime configuration.",
)


@app.command("show")
def show(ctx: typer.Context) -> None:
    """Show effective backend mode and selected global options."""
    opts = get_global_options(ctx)
    payload = {
        "mode": os.environ.get("DATAM8_MODE") or "server",
        "solutionPath": opts.solution,
        "logLevel": opts.log_level,
        "noLock": opts.no_lock,
    }
    emit_result(opts, payload)
