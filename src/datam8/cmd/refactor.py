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
from datam8.core.refactor import refactor_entity_id, refactor_keys, refactor_values
from datam8.core.workspace_io import read_solution, refactor_properties

from .common import (
    emit_result,
    lock_context,
    make_global_options,
    read_json_arg,
    resolve_solution_path,
)

app = typer.Typer(
    name="refactor",
    add_completion=False,
    no_args_is_help=True,
    help="Refactor keys, values, entity IDs, and custom properties.",
)


@app.command("properties")
def properties(
    property_renames: str = typer.Option("[]", "--property-renames"),
    value_renames: str = typer.Option("[]", "--value-renames"),
    deleted_properties: str = typer.Option("[]", "--deleted-properties"),
    deleted_values: str = typer.Option("[]", "--deleted-values"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Refactor property/value references in Base and Model JSON files."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    prop_renames = read_json_arg(property_renames)
    val_renames = read_json_arg(value_renames)
    del_props = read_json_arg(deleted_properties)
    del_vals = read_json_arg(deleted_values)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        result = refactor_properties(
            solution_path=active_solution_path,
            property_renames=prop_renames,
            value_renames=val_renames,
            deleted_properties=del_props,
            deleted_values=del_vals,
        )
    payload = {"status": "refactored", "result": result.model_dump()}
    emit_result(opts, payload, human_lines=["ok"])


@app.command("keys")
def keys(
    mapping_json: str = typer.Argument(..., help="JSON object of {oldKey:newKey}."),
    apply: bool = typer.Option(False, "--apply", help="Apply changes (default is dry-run)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Refactor object keys across Base and Model JSON files."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    mapping = read_json_arg(mapping_json)
    if apply:
        resolved, _ = read_solution(active_solution_path)
        with lock_context(opts=opts, lock_file_root=resolved.root_dir):
            result = refactor_keys(solution_path=active_solution_path, renames=dict(mapping), apply=True)
    else:
        result = refactor_keys(solution_path=active_solution_path, renames=dict(mapping), apply=False)
    payload = {"dryRun": not apply, "result": result}
    emit_result(opts, payload, human_lines=[f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})"])


@app.command("values")
def values(
    old: str = typer.Argument(..., help="Old string value."),
    new: str = typer.Argument(..., help="New string value."),
    key: str | None = typer.Option(None, "--key"),
    apply: bool = typer.Option(False, "--apply", help="Apply changes (default is dry-run)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Refactor string values globally or for a specific key."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    if apply:
        resolved, _ = read_solution(active_solution_path)
        with lock_context(opts=opts, lock_file_root=resolved.root_dir):
            result = refactor_values(solution_path=active_solution_path, old=old, new=new, key=key, apply=True)
    else:
        result = refactor_values(solution_path=active_solution_path, old=old, new=new, key=key, apply=False)
    payload = {"dryRun": not apply, "result": result}
    emit_result(opts, payload, human_lines=[f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})"])


@app.command("entity-id")
def entity_id(
    old: int = typer.Argument(...),
    new: int = typer.Argument(...),
    apply: bool = typer.Option(False, "--apply", help="Apply changes (default is dry-run)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Refactor entity IDs and their references."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    if apply:
        resolved, _ = read_solution(active_solution_path)
        with lock_context(opts=opts, lock_file_root=resolved.root_dir):
            result = refactor_entity_id(solution_path=active_solution_path, old=old, new=new, apply=True)
    else:
        result = refactor_entity_id(solution_path=active_solution_path, old=old, new=new, apply=False)
    payload = {"dryRun": not apply, "result": result}
    emit_result(opts, payload, human_lines=[f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})"])
