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

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer


class LogLevels(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


Lazy = Annotated[
    bool,
    typer.Option(
        "--lazy",
        help=(
            "Resolve properties only when access. "
            "Use with care as problems can occure when resolving properties in parallel."
        ),
    ),
]


LogLevel = Annotated[
    LogLevels,
    typer.Option(
        "--log-level",
        "-l",
        help="Set log level",
        envvar="DATAM8_LOG_LEVEL",
    ),
]


SolutionPath = Annotated[
    Path,
    typer.Option(
        ...,
        "--solution",
        "-s",
        "--solution-path",
        help="Path to .dm8s solution file (or folder containing exactly one .dm8s file)",
        envvar="DATAM8_SOLUTION_PATH",
    ),
]

GeneratorTarget = Annotated[
    str,
    typer.Argument(
        help="Target name as defined in .dm8s file",
        envvar="DATAM8_GENERATOR_TARGET",
    ),
]

AllTargets = Annotated[
    bool,
    typer.Option(
        "--all",
        help="Generates all targets in sequence",
        envvar="DATAM8_GENERATE_ALL_TARGETS",
    ),
]

CleanOutput = Annotated[
    bool,
    typer.Option(
        "--clean-output",
        "-c",
        help="Cleans the output directory, i.e. deleting its content",
        envvar="DATAM8_CLEAN_OUTPUT",
    ),
]

Payload = Annotated[
    list[str],
    typer.Option(
        "--payload",
        "-p",
        help="The name of a payload registrated via decorator. Can be provided multiple times",
    ),
]

MigrationOutputDir = Annotated[
    Path,
    typer.Option(
        "--output-dir",
        help="Directory where the migrated model will be written to",
    ),
]
