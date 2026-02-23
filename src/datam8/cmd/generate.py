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

import rich
import typer

from datam8 import config, factory, generate, logging, opts

logger = logging.getLogger(__name__)
app = typer.Typer(
    name="generate",
    add_completion=False,
    no_args_is_help=False,
    help="Generate a jinja2 template configured in the solution file.",
)


@app.callback(invoke_without_command=True)
def command(
    solution_path: opts.SolutionPath,
    target: opts.GeneratorTarget = opts.default_target,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    clean_output: opts.CleanOutput = False,
    payloads: opts.Payload = [],
    generate_all: opts.AllTargets = False,
    lazy: opts.Lazy = False,
):
    """Generate a jinja2 template configured in the solution file."""

    config.log_level = log_level
    config.lazy = lazy

    config.set_solution(solution_path)
    logging.setup_logger()

    if generate_all:
        logger.warning("The --all option is set, but is currently ignored.")

    model = factory.create_model_or_exit(config.solution_path)
    _ = generate.generate_output(
        model,
        target=target,
        payloads=payloads,
        generate_all=generate_all,
        clean_output=clean_output,
    )

    rich.print("Generation successfull")
