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
from datam8.core.entity_resolution import resolve_model_entity
from datam8.core.errors import Datam8ValidationError
from datam8.core.jsonops import merge_patch, set_by_pointer
from datam8.core.workspace_io import (
    create_model_entity,
    delete_model_entity,
    duplicate_model_entity,
    list_model_entities,
    move_model_entity,
    read_solution,
    read_workspace_json,
    rename_folder,
    write_model_entity,
)

from .common import (
    emit_result,
    lock_context,
    make_global_options,
    open_in_editor,
    read_json_arg,
    resolve_solution_path,
)

app = typer.Typer(
    name="model",
    add_completion=False,
    no_args_is_help=True,
    help="Read and edit Model entities.",
)


@app.command("list")
def list_entities(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List model entities."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    entities = list_model_entities(resolve_solution_path(opts))
    payload = {"count": len(entities), "entities": [e.model_dump() for e in entities]}
    emit_result(opts, payload, human_lines=[e.relPath for e in entities])


@app.command("get")
def get_entity(
    selector: str = typer.Argument(..., help="Entity selector (relPath, locator, id, or name)."),
    by: str = typer.Option("auto", "--by", help="Selector type: auto|relPath|locator|id|name."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Read a model entity JSON document."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    content = read_workspace_json(entity.rel_path, active_solution_path)
    payload = {"entity": entity.rel_path, "content": content}
    emit_result(opts, payload, human_lines=[json.dumps(content, indent=2, ensure_ascii=False)])


@app.command("create")
def create_entity(
    rel_path: str = typer.Argument(..., help="New entity relPath under Model/."),
    name: str | None = typer.Option(None, "--name", help="Optional entity name."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Create a new model entity JSON file."""
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
        abs_path = create_model_entity(rel_path, name=name, solution_path=active_solution_path)
    payload = {"status": "created", "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"created: {abs_path}"])


@app.command("save")
def save_entity(
    selector: str = typer.Argument(..., help="Entity selector (relPath, locator, id, or name)."),
    content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
    by: str = typer.Option("auto", "--by"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Overwrite a model entity JSON file."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    doc = read_json_arg(content)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = write_model_entity(entity.rel_path, doc, active_solution_path)
    payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("validate")
def validate_entity(
    selector: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Validate that a model entity is a JSON object."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    content = read_workspace_json(entity.rel_path, active_solution_path)
    if not isinstance(content, dict):
        raise Datam8ValidationError(message="Model entity must be a JSON object.", details={"relPath": entity.rel_path})
    emit_result(opts, {"status": "ok", "relPath": entity.rel_path}, human_lines=[f"ok: {entity.rel_path}"])


@app.command("set")
def set_pointer(
    selector: str = typer.Argument(...),
    pointer: str = typer.Argument(...),
    value_json: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    create_missing: bool = typer.Option(True, "--create-missing/--no-create-missing"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Set a JSON pointer value inside a model entity and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    current = read_workspace_json(entity.rel_path, active_solution_path)
    value = read_json_arg(value_json)
    next_doc = set_by_pointer(current, pointer, value, create_missing=create_missing)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = write_model_entity(entity.rel_path, next_doc, active_solution_path)
    payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("patch")
def patch_entity(
    selector: str = typer.Argument(...),
    patch_json: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Apply JSON merge-patch to a model entity and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    current = read_workspace_json(entity.rel_path, active_solution_path)
    patch = read_json_arg(patch_json)
    next_doc = merge_patch(current, patch)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = write_model_entity(entity.rel_path, next_doc, active_solution_path)
    payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("delete")
def delete_entity(
    selector: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Delete a model entity JSON file."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = delete_model_entity(entity.rel_path, active_solution_path)
    payload = {"status": "deleted", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])


@app.command("move")
def move_entity(
    from_rel_path: str = typer.Argument(...),
    to_rel_path: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Move or rename a model entity path."""
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
        result = move_model_entity(from_rel_path, to_rel_path, active_solution_path)
    payload = {"status": "moved", **result.model_dump()}
    emit_result(
        opts,
        payload,
        human_lines=[f"moved: {result.fromAbsPath} -> {result.toAbsPath}"],
    )


@app.command("duplicate")
def duplicate_entity(
    from_rel_path: str = typer.Argument(...),
    to_rel_path: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Duplicate a model entity JSON file."""
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
        result = duplicate_model_entity(from_rel_path, to_rel_path, solution_path=active_solution_path)
    payload = {"status": "duplicated", **result.model_dump()}
    emit_result(
        opts,
        payload,
        human_lines=[f"duplicated: {result.fromAbsPath} -> {result.toAbsPath}"],
    )


@app.command("folder-rename")
def rename_model_folder(
    from_folder_rel_path: str = typer.Argument(...),
    to_folder_rel_path: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Rename a model folder path."""
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
        result = rename_folder(from_folder_rel_path, to_folder_rel_path, active_solution_path)
    payload = {"status": "renamed", **result.model_dump()}
    emit_result(opts, payload, human_lines=[f"renamed: {result.fromAbsPath} -> {result.toAbsPath}"])


@app.command("edit")
def edit_entity(
    selector: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Open a model entity JSON in $EDITOR and save it."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    current = read_workspace_json(entity.rel_path, active_solution_path)
    edited_raw = open_in_editor(suffix=".json", initial_text=json.dumps(current, indent=4, ensure_ascii=False) + "\n")
    next_doc = json.loads(edited_raw)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = write_model_entity(entity.rel_path, next_doc, active_solution_path)
    payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
