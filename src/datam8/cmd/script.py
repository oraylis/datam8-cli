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
from datam8.core.entity_resolution import resolve_model_entity
from datam8.core.workspace_io import (
    delete_function_source,
    list_function_sources,
    read_function_source,
    read_solution,
    rename_function_source,
    write_function_source,
)

from .common import (
    emit_result,
    lock_context,
    make_global_options,
    read_text_arg,
    resolve_solution_path,
)

app = typer.Typer(
    name="script",
    add_completion=False,
    no_args_is_help=True,
    help="Manage function source files under Model/.",
)


@app.command("list")
def list_scripts(
    entity_selector: str = typer.Argument(..., help="Model entity selector owning the scripts."),
    by: str = typer.Option("auto", "--by"),
    entity_name: str | None = typer.Option(None, "--entity-name", help="Optional entity name hint."),
    referenced_only: bool = typer.Option(False, "--referenced-only", help="Only include referenced scripts."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List scripts for a model entity."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(entity_selector, solution_path=active_solution_path, by=by)
    scripts = list_function_sources(
        entity.rel_path,
        active_solution_path,
        entity_name,
        include_unreferenced=not referenced_only,
    )
    payload = {"entity": entity.rel_path, "count": len(scripts), "scripts": scripts}
    emit_result(opts, payload, human_lines=scripts)


@app.command("get")
def get_script(
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: str | None = typer.Option(None, "--entity-name"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Read a script for a model entity."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(entity_selector, solution_path=active_solution_path, by=by)
    content = read_function_source(entity.rel_path, source, active_solution_path, entity_name)
    payload = {"entity": entity.rel_path, "source": source, "content": content}
    emit_result(opts, payload, human_lines=[content])


@app.command("save")
def save_script(
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    content: str = typer.Argument(..., help="Script content, @file, or '-' for stdin."),
    by: str = typer.Option("auto", "--by"),
    entity_name: str | None = typer.Option(None, "--entity-name"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Write a script for a model entity."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    script_content = read_text_arg(content)
    entity = resolve_model_entity(entity_selector, solution_path=active_solution_path, by=by)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = write_function_source(
            entity.rel_path,
            source,
            script_content,
            active_solution_path,
            entity_name,
        )
    payload = {"status": "saved", "source": source, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])


@app.command("rename")
def rename_script(
    entity_selector: str = typer.Argument(...),
    from_source: str = typer.Argument(...),
    to_source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: str | None = typer.Option(None, "--entity-name"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Rename a script for a model entity."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(entity_selector, solution_path=active_solution_path, by=by)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        result = rename_function_source(
            entity.rel_path,
            from_source,
            to_source,
            active_solution_path,
            entity_name,
        )
    payload = {"status": "renamed", **result.model_dump()}
    emit_result(
        opts,
        payload,
        human_lines=[f"renamed: {result.fromAbsPath} -> {result.toAbsPath}"],
    )


@app.command("delete")
def delete_script(
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: str | None = typer.Option(None, "--entity-name"),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Delete a script for a model entity."""
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution_path = resolve_solution_path(opts)
    entity = resolve_model_entity(entity_selector, solution_path=active_solution_path, by=by)
    resolved, _ = read_solution(active_solution_path)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        abs_path = delete_function_source(entity.rel_path, source, active_solution_path, entity_name)
    payload = {"status": "deleted", "source": source, "absPath": abs_path}
    emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])
