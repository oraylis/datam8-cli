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
import dataclasses
import os
from collections.abc import Callable, Sequence
from concurrent import futures
from pathlib import Path
from typing import Protocol

import jinja2
from pydantic import BaseModel

from datam8_model.solution import GeneratorTarget

from . import config, factory, model, model_exceptions, opts, utils
from .core.paths import resolve_solution
from .utils import cache, importer

logger = utils.start_logger(__name__)
payload_functions: dict["PayloadOrder", list["PayloadDefinition"]] = {}

type PayloadFunction = Callable[[model.Model, cache.Cache], Sequence[IPayload]]
type PayloadOrder = int


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

    parsed_model = factory.create_model_or_raise()
    payload_cache = cache.Cache()

    if generate_all:
        logger.warning("The --all option is set, but is currently ignored.")

    try:
        if target == "none":

            def filter_targets(_target: GeneratorTarget) -> bool:
                if _target.isDefault is None:
                    return False
                return _target.isDefault

            generator_target = [_t for _t in parsed_model.solution.generatorTargets if filter_targets(_t)].pop()
        else:
            generator_target = parsed_model.get_generator_target(target)

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
                for payload in payload_functions[order]
                if payload.name in payloads or not payloads
            ]
            for order in sorted(payload_functions)
        }

        for order in selected_payloads:
            executor = futures.ThreadPoolExecutor()

            def render_payload_for_order(payload: PayloadDefinition) -> Exception | None:
                return asyncio.run(render_payload(payload, parsed_model, payload_cache))

            results = executor.map(render_payload_for_order, selected_payloads[order])
            executor.shutdown()
            errors = [_result for _result in results if _result]
            if errors:
                raise RenderError()
    except model_exceptions.InvalidGeneratorTargetError as err:
        logger.error(err)
        raise

    return GenerateResult(
        status="succeeded",
        target=target if target != "none" else "default",
        outputPath=str(output_path_abs),
    )


def register_payload(
    template: Path | str, order: int = 1
) -> Callable[[PayloadFunction], PayloadFunction]:
    """Register payload.

    Parameters
    ----------
    template : Path | str
        template parameter value.
    order : int
        order parameter value.

    Returns
    -------
    Callable[[PayloadFunction], PayloadFunction]
        Computed return value.

    Raises
    ------
    PayloadRegisteredMultipleTimesError
        Raised when validation or runtime execution fails."""
    def register_payload(func: PayloadFunction) -> PayloadFunction:
        logger.debug(f"Registering payload {func.__module__}:{func.__name__}")

        if func.__name__ in [
            payload.name
            for payloads in payload_functions.values()
            for payload in payloads
        ]:
            raise PayloadRegisteredMultipleTimesError(func.__name__)

        if order not in payload_functions:
            payload_functions[order] = []

        payload_functions[order].append(
            PayloadDefinition(
                name=func.__name__,
                _function=func,
                template_path=template if isinstance(template, Path) else Path(template),
                order=order,
            )
        )
        return func

    return register_payload


# @utils.print_progress_async("Rendering templates...")
@utils.get_logger
async def render_payload(
    payload: "PayloadDefinition", model: model.Model, cache: cache.Cache
) -> Exception | None:
    """Render payload.

    Parameters
    ----------
    payload : 'PayloadDefinition'
        payload parameter value.
    model : model.Model
        model parameter value.
    cache : cache.Cache
        cache parameter value.

    Returns
    -------
    Exception | None
        Computed return value.

    Raises
    ------
    Exception
        Raised when validation or runtime execution fails."""
    logger.debug(f"Render payload: {payload._function.__name__}")

    try:
        payloads: Sequence[IPayload] = payload._function(model, cache)
    except Exception as err:
        logger.error(
            "payload '{payload}' threw errors during payload creation: {error_type} - {msg}".format(  # noqa: UP032
                payload=payload.name,
                error_type=type(err).__name__,
                msg=err,
            )
        )
        return err

    template_loader = jinja2.FileSystemLoader(
        [config.solution_folder_path / config.template_path, config.solution_folder_path]
    )
    template_env = jinja2.Environment(loader=template_loader)
    template_path = config.template_path / payload.template_path

    try:
        template = template_env.get_template(template_path.as_posix())
    except jinja2.TemplateNotFound as err:
        logger.error(f"{payload.name}: {err}")
        return err

    coros = [
        render_template(payload.name, _p.get_data(), template, _p.get_output_path())
        for _p in payloads
    ]
    results = [
        result
        for result in await asyncio.gather(*coros, return_exceptions=True)
        if result is not None
    ]

    if len(results) > 0:
        raise Exception(results)

    logger.info(f"Rendered template {payload.template_path} from payload {payload.name}")
    return None


async def render_template(
    payload_name: str, data: object, template: jinja2.Template, output_path: Path
) -> None | Exception:
    """Render template.

    Parameters
    ----------
    payload_name : str
        payload_name parameter value.
    data : object
        data parameter value.
    template : jinja2.Template
        template parameter value.
    output_path : Path
        output_path parameter value.

    Returns
    -------
    None | Exception
        Computed return value."""
    _output_path = config.solution_folder_path / config.output_path / output_path
    logger.debug(f"[{payload_name}] Write output {template.filename} -> {_output_path}")

    output = template.render(data=data)

    if not _output_path.exists():
        os.makedirs(_output_path.parent, exist_ok=True)

    with open(_output_path, "w") as file:
        file.write(output)

    return None


@dataclasses.dataclass
class PayloadDefinition:
    name: str
    _function: PayloadFunction
    template_path: Path
    order: int


@dataclasses.dataclass
class BasePayload:
    data: object
    output_path: Path

    def get_data(self) -> object:
        return self.data

    def get_output_path(self) -> Path:
        return self.output_path


class IPayload(Protocol):
    def get_data(self) -> object: ...
    def get_output_path(self) -> Path: ...


class PayloadRegisteredMultipleTimesError(Exception):
    def __init__(self, payload_name):
        super().__init__(f"Payload [{payload_name}] already registered.")


class RenderError(Exception):
    def __init__(self):
        super().__init__("Error during payload rendering")
