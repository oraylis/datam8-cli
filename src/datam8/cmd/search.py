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
from datam8.core.search import search_entities, search_text

from .common import emit_result, make_global_options, resolve_solution_path

app = typer.Typer(
    name="search",
    add_completion=False,
    no_args_is_help=True,
    help="Search entities and text in a solution.",
)


@app.command("entities")
def search_entities_cmd(
    query: str = typer.Argument(..., help="Substring query."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Search entity names, locators, and paths."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    result = search_entities(solution_path=resolve_solution_path(opts), query=query)
    payload = {"query": query, **result}
    human_lines = [e.get("relPath", "") for e in result.get("entities") or []]
    emit_result(opts, payload, human_lines=human_lines)


@app.command("text")
def search_text_cmd(
    pattern: str = typer.Argument(..., help="Text pattern to find."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Search raw text within solution JSON files."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    result = search_text(solution_path=resolve_solution_path(opts), pattern=pattern)
    payload = {"pattern": pattern, **result}
    human_lines = [f"{m['file']}: {m['count']}" for m in result.get("matches") or []]
    emit_result(opts, payload, human_lines=human_lines)
