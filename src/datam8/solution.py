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
from pathlib import Path

from datam8 import config, model, utils
from datam8_model import solution as s


def init_solution(solution_path: Path) -> None:
    solution = s.Solution(
        schemaVersion=config.latest_schema_version(),  # take newest/left version
        modelPath=Path("model"),
        basePath=Path("base"),
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

    base_dirs = ["model", "base", "generate", "output"]
    for dir in base_dirs:
        utils.mkdir(solution_path.parent / dir)
