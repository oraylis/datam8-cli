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
from pydantic import ValidationError

from datam8 import opts as cli_opts
from datam8.core import workspace_service
from datam8.core.entity_resolution import resolve_model_entity
from datam8.core.errors import Datam8ValidationError
from datam8.core.jsonops import merge_patch, set_by_pointer
from datam8.core.workspace_io import read_workspace_json
from datam8_model import model as model_model

from .common import (
    emit_result,
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

folder_metadata_app = typer.Typer(
    name="folder-metadata",
    add_completion=False,
    no_args_is_help=True,
    help="Read and edit Model folder metadata files (*.properties.json).",
)
app.add_typer(folder_metadata_app, name="folder-metadata")


@app.command("list")
def list_entities(
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List model entities."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    entities = workspace_service.list_model_entities(resolve_solution_path(opts))
    payload = {"count": len(entities), "entities": [e.model_dump(mode="json") for e in entities]}
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
    abs_path = workspace_service.create_model_entity(
        rel_path=rel_path,
        name=name,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    """Validate that a model entity matches the schema."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
    content = read_workspace_json(entity.rel_path, active_solution_path)
    try:
        model_model.ModelEntity.model_validate(content)
    except ValidationError as e:
        raise Datam8ValidationError(
            message="Model entity validation failed.",
            details={"relPath": entity.rel_path, "errors": e.errors()},
        )
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
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    abs_path = workspace_service.delete_model_entity(
        rel_path=entity.rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    result = workspace_service.move_model_entity(
        from_rel_path=from_rel_path,
        to_rel_path=to_rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    result = workspace_service.duplicate_model_entity(
        from_rel_path=from_rel_path,
        to_rel_path=to_rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
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
    """Rename a model folder path and regenerate index."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    result = workspace_service.rename_model_folder(
        from_folder_rel_path=from_folder_rel_path,
        to_folder_rel_path=to_folder_rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {
        "status": "renamed",
        "fromAbsPath": result.fromAbsPath,
        "toAbsPath": result.toAbsPath,
        "entities": [entity.model_dump(mode="json") for entity in result.entities],
        "index": result.index,
    }
    emit_result(
        opts,
        payload,
        human_lines=[
            f"renamed: {result.fromAbsPath} -> {result.toAbsPath}",
            f"modelEntities: {len(result.entities)}",
        ],
    )


@folder_metadata_app.command("get")
def get_folder_metadata(
    rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Read a folder metadata JSON document."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    content = workspace_service.read_folder_metadata(
        rel_path=rel_path,
        solution_path=active_solution_path,
    )
    content_payload = content.model_dump(mode="json")
    payload = {"relPath": rel_path, "content": content_payload}
    emit_result(opts, payload, human_lines=[json.dumps(content_payload, indent=2, ensure_ascii=False)])


@folder_metadata_app.command("save")
def save_folder_metadata_cmd(
    rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
    content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Write a folder metadata JSON document."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    doc = read_json_arg(content)
    abs_path = workspace_service.save_folder_metadata(
        rel_path=rel_path,
        content=doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "relPath": rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@folder_metadata_app.command("delete")
def delete_folder_metadata_cmd(
    rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Delete a folder metadata JSON document."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    abs_path = workspace_service.delete_folder_metadata(
        rel_path=rel_path,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "deleted", "relPath": rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])


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
    abs_path = workspace_service.save_model_entity(
        rel_path=entity.rel_path,
        content=next_doc,
        solution_path=active_solution_path,
        no_lock=opts.no_lock,
        lock_timeout=opts.lock_timeout,
    )
    payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
