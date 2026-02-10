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

from datam8.core.solution_files import detect_solution_version
from datam8.core.workspace_io import (
    create_new_project,
    list_base_entities,
    list_model_entities,
    read_solution,
)

from .common import emit_result, get_global_options, resolve_solution_path

app = typer.Typer(
    name="solution",
    add_completion=False,
    no_args_is_help=True,
    help="Inspect and create solution workspaces.",
)


@app.command("inspect")
def inspect_solution(
    ctx: typer.Context,
    path: str = typer.Option(..., "--path", help="Path to a solution file."),
) -> None:
    """Detect whether a solution path is v1 or v2."""
    opts = get_global_options(ctx)
    version = detect_solution_version(path)
    emit_result(opts, {"version": version}, human_lines=[version])


@app.command("info")
def solution_info(ctx: typer.Context) -> None:
    """Show resolved solution metadata."""
    opts = get_global_options(ctx)
    resolved, sol = read_solution(resolve_solution_path(opts))
    payload = {
        "solutionPath": str(resolved.solution_file),
        "solution": sol.model_dump(),
        "resolvedPaths": {"base": sol.basePath, "model": sol.modelPath},
    }
    emit_result(
        opts,
        payload,
        human_lines=[
            f"solution: {resolved.solution_file}",
            f"schemaVersion: {sol.schemaVersion}",
            f"basePath: {sol.basePath}",
            f"modelPath: {sol.modelPath}",
        ],
    )


@app.command("full")
def solution_full(ctx: typer.Context) -> None:
    """Show solution metadata plus base/model entity listings."""
    opts = get_global_options(ctx)
    solution_path = resolve_solution_path(opts)
    resolved, sol = read_solution(solution_path)
    base_entities = [e.__dict__ for e in list_base_entities(solution_path)]
    model_entities = [e.__dict__ for e in list_model_entities(solution_path)]
    payload = {
        "solutionPath": str(resolved.solution_file),
        "solution": sol.model_dump(),
        "baseEntities": base_entities,
        "modelEntities": model_entities,
    }
    emit_result(
        opts,
        payload,
        human_lines=[
            f"solution: {resolved.solution_file}",
            f"baseEntities: {len(base_entities)}",
            f"modelEntities: {len(model_entities)}",
        ],
    )


@app.command("validate")
def validate_solution(ctx: typer.Context) -> None:
    """Validate that the solution exists and matches schema."""
    opts = get_global_options(ctx)
    resolved, _ = read_solution(resolve_solution_path(opts))
    payload = {"status": "ok", "solutionPath": str(resolved.solution_file)}
    emit_result(opts, payload, human_lines=[f"ok: {resolved.solution_file}"])


@app.command("new-project")
def solution_new_project(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Solution/project name."),
    root: str = typer.Option(..., "--root", help="Directory where the project will be created."),
    target: str = typer.Option(..., "--target", help="Generator target name."),
    base_path: str | None = typer.Option(None, "--base-path", help="Base folder name (default: Base)."),
    model_path: str | None = typer.Option(None, "--model-path", help="Model folder name (default: Model)."),
) -> None:
    """Create a new minimal v2 project structure."""
    opts = get_global_options(ctx)
    solution_path = create_new_project(
        solution_name=name,
        project_root=root,
        base_path=base_path,
        model_path=model_path,
        target=target,
    )
    payload = {"solutionPath": solution_path}
    emit_result(opts, payload, human_lines=[solution_path])
