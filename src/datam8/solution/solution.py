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

import io
import os
import shutil
import urllib.request
import zipfile
from http.client import HTTPResponse
from importlib import resources
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from datam8 import config, errors, model, utils
from datam8_model import base as b
from datam8_model import solution as s

SAMPLE_SOLUTION_VERSION: Final[str] = "2.0.0-beta.1"
SAMPLE_SOLUTION_REPO_URL: Final[str] = "https://github.com/oraylis/datam8-sample-solution"
SAMPLE_SOLUTION_DOWNLOAD_URL: Final[str] = (
    f"{SAMPLE_SOLUTION_REPO_URL}/archive/refs/tags/v{SAMPLE_SOLUTION_VERSION}.zip"
)


def _copy_default_base_entities(base_path: Path) -> None:
    standard_files_path = resources.files("datam8.solution")

    # generate a list of default file names
    files = [
        f"{kind.value[0].upper() + kind.value[1:]}.json"
        for kind in b.EntityType
        # except models, folders and data_modules, as those are handled differently
        if kind
        not in (b.EntityType.MODEL_ENTITIES, b.EntityType.FOLDERS, b.EntityType.DATA_MODULES)
    ]

    for file_name in files:
        src_path = standard_files_path.joinpath(file_name)
        shutil.copy(str(src_path), base_path / file_name)


def init_solution(solution_path: Path, settings: dict[str, Any] | None = None) -> None:
    default_solution = s.Solution(
        schemaVersion=config.latest_schema_version(),  # take newest/left version
        modelPath=Path("model"),
        basePath=Path("base"),
        pluginsPath=Path("plugins"),
        generatorTargets=[
            s.GeneratorTarget(
                name="default",
                sourcePath=Path("generate"),
                outputPath=Path("output"),
                isDefault=True,
            )
        ],
    )
    values = default_solution.model_dump(mode="json", by_alias=True, exclude_unset=True)
    settings = settings or {}
    if "schemaVersion" in settings or "schema_version" in settings:
        raise errors.Datam8ValidationError(message="schemaVersion is managed by migrations")
    values.update(settings)
    try:
        solution = s.Solution.model_validate(values)
    except ValidationError as err:
        raise errors.Datam8ValidationError(message=f"Invalid solution settings: {err}") from err

    solution_root = solution_path.parent.resolve()
    solution_dirs = [solution.basePath, solution.modelPath, solution.pluginsPath]
    if solution.diagramPath:
        solution_dirs.append(solution.diagramPath)
    for target in solution.generatorTargets:
        solution_dirs.extend((target.sourcePath, target.outputPath))
    directories = {solution_root / directory for directory in solution_dirs}
    for directory in directories:
        if not directory.resolve().is_relative_to(solution_root):
            raise errors.Datam8ValidationError(
                message="Solution paths must stay inside the solution directory"
            )

    utils.mkdir(solution_path.parent, recursive=True)

    with open(solution_path, "x", encoding="utf-8", newline="\n") as _f:
        _f.write(solution.model_dump_json(**model.MODEL_DUMP_OPTIONS))

    for directory in directories:
        utils.mkdir(directory, recursive=True)
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            with open(gitkeep, "x", encoding="utf-8") as _f:
                _f.write("")

    _copy_default_base_entities(solution_root / solution.basePath)


def init_solution_from_sample(solution_path: Path) -> str:
    "Downloads the sample solution and returns the initialed version"
    try:
        # urlopen() raises an exception for non-200 status codes
        with urllib.request.urlopen(SAMPLE_SOLUTION_DOWNLOAD_URL) as response:
            assert isinstance(response, HTTPResponse), (  # technically not possible?
                f"Received a non-http response from {SAMPLE_SOLUTION_DOWNLOAD_URL}"
            )
            data = response.read()
    except Exception as err:
        raise utils.create_error(f"Could not download sample solution: {err}")

    with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
        zip_file.extractall(solution_path.parent)

    # the repository is in a sub directory, so its needs to be moved one directory up
    for _sub in (solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}").glob(
        "*"
    ):
        shutil.move(_sub, solution_path.parent)

    # cleanup now empty dir
    os.rmdir(solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}/")

    return SAMPLE_SOLUTION_VERSION
