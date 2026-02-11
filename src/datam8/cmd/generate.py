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

import asyncio
import sys
from collections.abc import Sequence
from concurrent import futures
from pathlib import Path

import rich
import typer
from pydantic import BaseModel

from datam8.model_exceptions import InvalidGeneratorTargetError
from datam8.utils.cache import Cache
from datam8_model.solution import GeneratorTarget

from .. import config, factory, generate, opts, utils
from ..core.paths import resolve_solution
from ..utils import importer

app = typer.Typer(
    name="generate",
    add_completion=False,
    no_args_is_help=False,
    help="Generate a jinja2 template configured in the solution file.",
)

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


class GenerateResult(BaseModel):
    """Typed result of a synchronous generation run."""

    status: str
    target: str
    outputPath: str


def run_generation(
    *,
    solution_path: Path,
    target: str,
    log_level: opts.LogLevels | str,
    clean_output: bool,
    payloads: Sequence[str],
    generate_all: bool,
    lazy: bool,
) -> GenerateResult:
    """Execute the generator synchronously and return metadata about the run."""
    if isinstance(log_level, str):
        try:
            log_level = opts.LogLevels(log_level.strip().lower())
        except Exception:
            log_level = opts.LogLevels.INFO

    resolved = resolve_solution(str(solution_path))
    config.log_level = log_level
    config.solution_path = resolved.solution_file
    config.lazy = lazy
    config.solution_folder_path = resolved.root_dir

    model = factory.create_model()
    cache = Cache()

    if generate_all:
        logger.warning("The --all option is set, but is currently ignored.")

    try:
        if target == "none":

            def filter_targets(_target: GeneratorTarget) -> bool:
                if _target.isDefault is None:
                    return False
                return _target.isDefault

            generator_target = [_t for _t in model.solution.generatorTargets if filter_targets(_t)].pop()
        else:
            generator_target = model.get_generator_target(target)

        config.template_path = generator_target.sourcePath
        config.output_path = generator_target.outputPath
        config.module_path = config.solution_folder_path / generator_target.sourcePath / "__modules"
        output_path_abs = config.solution_folder_path / config.output_path

        importer.enable_target_modules()
        _ = importer.load_modules(config.module_path)

        if clean_output and output_path_abs.exists():
            logger.warning("Cleaning output...")
            utils.delete_path(output_path_abs, recursive=True)

        if not output_path_abs.exists():
            utils.mkdir(output_path_abs, recursive=True)

        selected_payloads = {
            order: [
                payload
                for payload in generate.payload_functions[order]
                if payload.name in payloads or not payloads
            ]
            for order in sorted(generate.payload_functions)
        }

        for order in selected_payloads:
            executor = futures.ThreadPoolExecutor()

            def render_payload(payload: generate.PayloadDefinition) -> Exception | None:
                return asyncio.run(generate.render_payload(payload, model, cache))

            results = executor.map(render_payload, selected_payloads[order])
            executor.shutdown()
            errors = [_result for _result in results if _result]
            if errors:
                raise generate.RenderError()
    except InvalidGeneratorTargetError as err:
        logger.error(err)
        raise

    return GenerateResult(
        status="succeeded",
        target=target if target != "none" else "default",
        outputPath=str(output_path_abs),
    )


@app.callback(invoke_without_command=True)
def command(
    solution_path: Path | None = typer.Option(
        None,
        "--solution",
        "-s",
        "--solution-path",
        help="Path to .dm8s solution file (or folder containing exactly one .dm8s file).",
        envvar="DATAM8_SOLUTION_PATH",
    ),
    target: opts.GeneratorTarget = config.target,
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        "-l",
        help="Set log level (defaults to global --log-level or DATAM8_LOG_LEVEL).",
        envvar="DATAM8_LOG_LEVEL",
    ),
    clean_output: opts.CleanOutput = False,
    payloads: opts.Payload = [],
    generate_all: opts.AllTargets = False,
    lazy: opts.Lazy = False,
):
    """Generate a jinja2 template configured in the solution file."""
    if solution_path is None:
        raise typer.BadParameter("No solution specified. Use --solution/-s (or set DATAM8_SOLUTION_PATH).")

    effective_log_level = log_level
    if not isinstance(effective_log_level, str) or not effective_log_level.strip():
        effective_log_level = opts.LogLevels.WARNING.value

    try:
        _ = run_generation(
            solution_path=solution_path,
            target=target,
            log_level=effective_log_level,
            clean_output=clean_output,
            payloads=payloads,
            generate_all=generate_all,
            lazy=lazy,
        )
    except Exception:
        sys.exit(1)

    rich.print("Generation successfull")
