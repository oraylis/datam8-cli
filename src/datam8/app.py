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

import os

import typer

from .cmd import (
    base,
    config_cmd,
    connector,
    datasource,
    fs,
    generate,
    index,
    migration,
    model,
    plugin,
    refactor,
    reverse,
    script,
    search,
    secret,
    serve,
    solution,
    validate,
)
from .cmd.common import build_global_options, version_callback

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=True,
    pretty_exceptions_short=False,
)

app.add_typer(solution.app)
app.add_typer(base.app)
app.add_typer(model.app)
app.add_typer(script.app)
app.add_typer(index.app)
app.add_typer(refactor.app)
app.add_typer(search.app)
app.add_typer(connector.app)
app.add_typer(plugin.app)
app.add_typer(secret.app)
app.add_typer(datasource.app)
app.add_typer(config_cmd.app)
app.add_typer(migration.app)
app.add_typer(fs.app)
app.add_typer(generate.app)
app.add_typer(validate.app)
app.add_typer(reverse.app)
app.add_typer(serve.app)


@app.callback()
def main_callback(
    ctx: typer.Context,
    solution_path: str | None = typer.Option(
        None,
        "--solution",
        "--solution-path",
        "-s",
        help="Path to .dm8s solution file (or folder containing exactly one .dm8s file).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce human-readable output."),
    verbose: bool = typer.Option(False, "--verbose", help="Increase human-readable output."),
    log_file: str | None = typer.Option(None, "--log-file", help="Optional log output file."),
    log_level: str = typer.Option("info", "--log-level", help="Global default log level."),
    lock_timeout: str = typer.Option("10s", "--lock-timeout", help="Solution lock timeout (e.g. 10s, 2m)."),
    no_lock: bool = typer.Option(False, "--no-lock", help="Disable solution lock (dangerous)."),
    version: bool = typer.Option(False, "--version", callback=version_callback, is_eager=True),
) -> None:
    """Configure global CLI options."""
    _ = version
    opts = build_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
        log_file=log_file,
        log_level=log_level,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    if opts.solution:
        os.environ["DATAM8_SOLUTION_PATH"] = opts.solution
    os.environ["DATAM8_LOG_LEVEL"] = opts.log_level
    ctx.obj = opts


def main() -> None:
    """Run the DataM8 CLI."""
    app()


if __name__ == "__main__":
    main()
