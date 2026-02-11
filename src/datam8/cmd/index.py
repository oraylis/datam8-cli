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

import json

import typer

from datam8 import opts as cli_opts
from datam8.core.indexing import read_index, validate_index
from datam8.core.workspace_io import read_solution, regenerate_index

from .common import emit_result, lock_context, make_global_options, resolve_solution_path

app = typer.Typer(
    name="index",
    add_completion=False,
    no_args_is_help=True,
    help="Read, validate, and regenerate the solution index.",
)


@app.command("regenerate")
def regenerate(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Regenerate .datam8-index.json for the active solution."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        index = regenerate_index(active_solution_path)
    payload = {"status": "index_regenerated", "index": index}
    emit_result(opts, payload, human_lines=["index regenerated"])


@app.command("validate")
def validate(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Validate the current index against model/base entities."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    report = validate_index(resolve_solution_path(opts))
    payload = {"status": "ok" if report.get("ok") else "error", "report": report}
    emit_result(
        opts,
        payload,
        human_lines=["ok"] if report.get("ok") else ["index validation failed"],
    )
    if not report.get("ok"):
        raise typer.Exit(code=2)


@app.command("show")
def show(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Show the current index JSON."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    index = read_index(resolve_solution_path(opts))
    payload = {"index": index}
    emit_result(opts, payload, human_lines=[json.dumps(index, indent=2, ensure_ascii=False)])
