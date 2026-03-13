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

import typer

from datam8 import opts
from datam8.core.runtime_meta import get_version

from .cmd import (
    base,
    config_cmd,
    connector,
    datasource,
    fs,
    generate,
    index,
    init,
    migration,
    model,
    plugin,
    refactor,
    script,
    search,
    secret,
    serve,
    solution,
    validate,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=True,
    pretty_exceptions_short=False,
)


@app.callback(invoke_without_command=True)
def _callback(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    if version:
        typer.echo(get_version())
        raise typer.Exit(code=0)


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
app.add_typer(serve.app)
app.add_typer(init.app)


if __name__ == "__main__":
    app()
