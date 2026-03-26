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
import zipfile
from pathlib import Path

import requests

from datam8 import config, model, utils
from datam8_model import solution as s

SAMPLE_SOLUTION_VERSION = "2.0.0-beta.1"
SAMPLE_SOLUTION_REPO_URL = "https://github.com/oraylis/datam8-sample-solution"


def init_solution(solution_path: Path) -> None:
    solution = s.Solution(
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

    utils.mkdir(solution_path.parent, recursive=True)

    with open(solution_path, "x") as _f:
        _f.write(solution.model_dump_json(**model.MODEL_DUMP_OPTIONS))

    base_dirs = ["model", "base", "generate", "output", "plugins"]
    for dir in base_dirs:
        utils.mkdir(solution_path.parent / dir)
        with open(solution_path.parent / dir / ".gitkeep", "x") as _f:
            _f.write("")


def init_solution_from_sample(solution_path: Path) -> str:
    "Downloads the sample solution and returns the initialed version"
    try:
        response = requests.get(
            f"{SAMPLE_SOLUTION_REPO_URL}/archive/refs/tags/v{SAMPLE_SOLUTION_VERSION}.zip"
        )
    except Exception as err:
        raise utils.create_error(f"Could not download sample solution: {err}")

    if response.status_code != 200:
        raise utils.create_error(f"Could not download sample solution: {response.status_code}")

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        zip_file.extractall(solution_path.parent)

    # the repsitory is in a sub directory, so its needs to be moved one directory up
    for _sub in (solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}").glob(
        "*"
    ):
        shutil.move(_sub, solution_path.parent)

    # cleanup now empty dir
    os.rmdir(solution_path.parent / f"datam8-sample-solution-{SAMPLE_SOLUTION_VERSION}/")

    return SAMPLE_SOLUTION_VERSION
