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

"""Read and maintain function-backed transformations without an editor."""

from typing import Annotated

import typer

from datam8 import errors, opts
from datam8.operations import Operation, relative_file

from . import common

app = typer.Typer(
    name="functions", help="Manage function sources and transformations", no_args_is_help=True
)
Step = Annotated[int | None, typer.Option(min=1)]
Name = Annotated[str | None, typer.Option()]


def _selector(step_no, name):
    if (step_no is None) == (name is None):
        raise errors.Datam8ValidationError(message="Provide exactly one of --step-no or --name")


@app.command("list")
@common.output
def list_(
    solution_path: opts.SolutionPath,
    locator: opts.Locator = "modelEntities",
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    session = common.session(solution_path, log_level, version)
    items = []
    for wrapper in session.model.get_entities(locator):
        for transformation in getattr(wrapper.entity, "transformations", []):
            if transformation.kind.value != "function":
                continue
            path = session.function_source(wrapper, transformation)
            items.append(
                {
                    "locator": str(wrapper.locator),
                    "stepNo": transformation.stepNo,
                    "name": transformation.name,
                    "sourceFile": relative_file(path),
                }
            )
    if not json_output:
        for item in items:
            typer.echo(
                f"{item['locator']}\n {item['stepNo']}. {item['name']}: {item['sourceFile']}"
            )
    return {"count": len(items), "items": items}


@app.command()
@common.output
def show(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    step_no: Step = None,
    name: Name = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _selector(step_no, name)
    session = common.session(solution_path, log_level, version)
    wrapper = session.model.get_entity_by_locator(locator)
    transformation = session.find_function(wrapper, step_no, name)
    path = session.function_source(wrapper, transformation)
    code = path.read_text(encoding="utf-8")
    if not json_output:
        typer.echo(
            f"# {'=' * 78}\n# file: {relative_file(path)}\n# name: {transformation.name}\n# stepNo: {transformation.stepNo}\n# {'=' * 78}\n{code}"
        )
    return {
        "item": {
            "locator": str(wrapper.locator),
            "stepNo": transformation.stepNo,
            "name": transformation.name,
            "sourceFile": relative_file(path),
            "sourceCode": code,
        }
    }


@app.command()
@common.output
def create(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    step_no: Annotated[int, typer.Option(min=1)],
    name: Annotated[str, typer.Option()],
    source: Annotated[str, typer.Option()],
    file: Annotated[str | None, typer.Option()] = None,
    code: Annotated[str | None, typer.Option()] = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    result = common.session(solution_path, log_level, version).execute(
        Operation(
            op="functions.create",
            locator=locator,
            data={
                "stepNo": step_no,
                "name": name,
                "kind": "function",
                "function": {"source": source},
            },
            source_code=common.input_value(code, file, text=True),
        )
    )
    if not json_output:
        typer.echo(f"Created '{name}' at '{source}'")
    return result


@app.command()
@common.output
def update(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    step_no: Step = None,
    name: Name = None,
    file: Annotated[str | None, typer.Option()] = None,
    code: Annotated[str | None, typer.Option()] = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _selector(step_no, name)
    result = common.session(solution_path, log_level, version).execute(
        Operation(
            op="functions.update",
            locator=locator,
            step_no=step_no,
            name=name,
            source_code=common.input_value(code, file, text=True),
        )
    )
    if not json_output:
        typer.echo("Function source updated")
    return result


@app.command()
@common.output
def delete(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    step_no: Step = None,
    name: Name = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _selector(step_no, name)
    result = common.session(solution_path, log_level, version).execute(
        Operation(op="functions.delete", locator=locator, step_no=step_no, name=name)
    )
    if not json_output:
        typer.echo("Function transformation removed")
    return result


@app.command()
@common.output
def move(
    locator: opts.Locator,
    new_location: opts.Path,
    solution_path: opts.SolutionPath,
    step_no: Step = None,
    name: Name = None,
    force: bool = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
):
    _selector(step_no, name)
    result = common.session(solution_path, log_level, version).execute(
        Operation(
            op="functions.move",
            locator=locator,
            step_no=step_no,
            name=name,
            new_path=new_location.as_posix(),
            force=force,
        )
    )
    if not json_output:
        typer.echo(f"Moved function to '{new_location}'")
    return result
