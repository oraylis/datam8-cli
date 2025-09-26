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
import sys
from collections.abc import Callable, Sequence
from importlib import util
from pathlib import Path
from types import ModuleType

import jinja2

from . import config, model, utils
from .utils import cache

logger = utils.start_logger(__name__)
payload_functions: dict["PayloadOrder", list["PayloadDefinition"]] = {}

type PayloadFunction = Callable[[model.Model, cache.Cache], Sequence[Payload]]
type PayloadOrder = int


def register_payload(
    template: Path | str, order: int = 1
) -> Callable[[PayloadFunction], PayloadFunction]:
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


@utils.get_logger
def load_modules(module_path: Path) -> dict[str, ModuleType]:
    modules: dict[str, ModuleType] = {}
    module_files = list(module_path.glob("**/*.py"))

    for i in range(0, len(module_files)):
        module_name = (
            module_files[i].relative_to(module_path).as_posix().removesuffix(".py")
        )
        try:
            modules[module_name] = load_module(module_files[i], module_name)
        except PayloadRegisteredMultipleTimesError as err:
            logger.error(f"{err}\n{module_files[i]}")
            sys.exit(1)

    logger.info(f"Loaded {len(modules)} modules with {len(payload_functions)} payload(s)")

    return modules


def load_module(path: Path, module_name: str) -> ModuleType:
    logger.debug(f"Loaded module {path.relative_to(config.solution_folder_path)}")

    spec = util.spec_from_file_location(module_name, path)
    if spec is None:
        # TODO: raise a better error
        raise Exception("spec is none")

    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader = spec.loader

    if loader is None:
        # TODO: raise a better error
        raise Exception("loader is none")

    loader.exec_module(module)

    return module


# @utils.print_progress_async("Rendering templates...")
async def render_payload(
    payload: "PayloadDefinition", model: model.Model, cache: cache.Cache
) -> Exception | None:
    logger.debug(f"Render payload: {payload._function.__name__}")

    try:
        payloads: Sequence[Payload] = payload._function(model, cache)
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
        render_template(payload.name, _p.data, template, _p.output_path)
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
class Payload:
    data: object
    output_path: Path


class PayloadRegisteredMultipleTimesError(Exception):
    def __init__(self, payload_name):
        super().__init__(f"Payload [{payload_name}] already registered.")


class RenderError(Exception):
    def __init__(self):
        super().__init__("Error during payload rendering")
