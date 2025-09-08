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
        "--solution-path",
        "-s",
        help="Path to .dm8s solution file",
        envvar="DATAM8_SOLUTION_PATH",
    ),
]

GeneratorTarget = Annotated[
    str,
    typer.Argument(
        help="Target name as defined in .dm8gs file",
        envvar="DATAM8_GENERATOR_TARGET",
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
