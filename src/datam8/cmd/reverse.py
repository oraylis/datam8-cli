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

from typing import Annotated

import typer

app = typer.Typer()


@app.command("reverse")
def command(
    data_source: Annotated[
        str | None,
        typer.Option(
            "--data-source",
            help="Name of the data source for reverse generation (required for reverse_generate).",
        ),
    ] = None,
    data_product: Annotated[
        str | None,
        typer.Option(
            "--data-product",
            help="Data product name for output path (required for reverse_generate).",
        ),
    ] = None,
    data_module: Annotated[
        str | None,
        typer.Option(
            "--data-module",
            help="Data module name for output path (required for reverse_generate).",
        ),
    ] = None,
    tables: Annotated[
        str | None,
        typer.Option(
            "--tables",
            help="Comma-separated list of table names to reverse generate (required for reverse_generate).",
        ),
    ] = None,
    entity_names: Annotated[
        str | None,
        typer.Option(
            "--entity-names",
            help="Comma-separated list of entity names corresponding to tables (optional for reverse_generate).",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            help="Enable interactive mode for reverse generation with user prompts.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Set log level: NOTSET, DEBUG, INFO, WARN, ERROR, CRITICAL (default INFO).",
        ),
    ] = "INFO",
):
    """Generate a datam8 model file from a source object."""
    ...
