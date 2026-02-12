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
from datam8.core import workspace_service
from datam8.core.jsonops import merge_patch, set_by_pointer
from datam8.core.workspace_io import read_workspace_json

from .common import (
    emit_result,
    make_global_options,
    open_in_editor,
    read_json_arg,
    resolve_solution_path,
)

app = typer.Typer(
    name="base",
    add_completion=False,
    no_args_is_help=True,
    help="Read and edit Base/*.json files.",
)


@app.command("list")
def list_entities(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List Base entities."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    entities = workspace_service.list_base_entities(resolve_solution_path(opts))
    payload = {"count": len(entities), "entities": [e.model_dump() for e in entities]}
    emit_result(opts, payload, human_lines=[e.relPath for e in entities])


@app.command("get")
def get_entity(
    rel_path: str = typer.Argument(..., help="Path relative to solution root."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Read a Base entity JSON document."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    content = read_workspace_json(rel_path, resolve_solution_path(opts))
    payload = {"relPath": rel_path, "content": content}
    emit_result(opts, payload, human_lines=[json.dumps(content, indent=2, ensure_ascii=False)])


@app.command("save")
def save_entity(
    rel_path: str = typer.Argument(...),
    content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Overwrite a Base entity JSON file."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    doc = read_json_arg(content)
    abs_path = workspace_service.save_base_entity(
        rel_path=rel_path,
        content=doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("set")
def set_pointer(
    rel_path: str = typer.Argument(..., help="Path relative to solution root."),
    pointer: str = typer.Argument(..., help="JSON pointer (e.g. /a/b/0)."),
    value_json: str = typer.Argument(..., help="JSON value (string, @file, or '-' for stdin)."),
    create_missing: bool = typer.Option(True, "--create-missing/--no-create-missing"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Set a JSON pointer value inside a Base entity and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    current = read_workspace_json(rel_path, active_solution_path)
    value = read_json_arg(value_json)
    next_doc = set_by_pointer(current, pointer, value, create_missing=create_missing)
    abs_path = workspace_service.save_base_entity(
        rel_path=rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("patch")
def patch_entity(
    rel_path: str = typer.Argument(..., help="Path relative to solution root."),
    patch_json: str = typer.Argument(..., help="JSON merge patch (string, @file, or '-' for stdin)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Apply JSON merge-patch to a Base entity and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    current = read_workspace_json(rel_path, active_solution_path)
    patch = read_json_arg(patch_json)
    next_doc = merge_patch(current, patch)
    abs_path = workspace_service.save_base_entity(
        rel_path=rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("edit")
def edit_entity(
    rel_path: str = typer.Argument(..., help="Path relative to solution root."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Open a Base JSON entity in $EDITOR and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    current = read_workspace_json(rel_path, active_solution_path)
    edited_raw = open_in_editor(suffix=".json", initial_text=json.dumps(current, indent=4, ensure_ascii=False) + "\n")
    next_doc = json.loads(edited_raw)
    abs_path = workspace_service.save_base_entity(
        rel_path=rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("delete")
def delete_entity(
    rel_path: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Delete a Base entity JSON file."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    abs_path = workspace_service.delete_base_entity(
        rel_path=rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "deleted", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])
