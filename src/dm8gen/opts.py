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
    typer.Argument(
        help="Path to .dm8s solution file",
        envvar="DATAM8_SOLUTION_PATH",
    ),
]
