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

"""
Utility Module to make working with datam8 models more comfortable in jinja2 templates.

### submodules
* cache
* hasher

### functions
* validate_json_schema
* read_json
* coalesce
* get_locator
* start_logger

### classes
* JsonFileParseException
* ColorFormatter
"""

import functools
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.progress import Progress, SpinnerColumn, TextColumn

from .. import config, opts


def none_if[T](input: T | None, value: T) -> T | None:
    if input == value:
        return None
    return input


def pascal_to_snake_case(text: str) -> str:
    """
    Convert a pascal or camel case string to snake case

    Example
    -------
    * `AttributeTypes.json` to `attribute_types.json`
    * `dataSources.json` to `data_sources.json`
    * `data_types.json` to `data_types.json`
    """
    result: list[str] = []

    for idx in range(0, len(text)):
        if text[idx].isupper() and idx != 0:
            result.append("_")

        result.append(text[idx].lower())

    return "".join(result)


def delete_path(path: Path, recursive: bool = False) -> None:
    """Delete path.

    Parameters
    ----------
    path : Path
        path parameter value.
    recursive : bool
        recursive parameter value.

    Returns
    -------
    None
        Computed return value."""
    if not path.exists():
        return

    if path.is_file():
        os.remove(path)
        return

    if not recursive and path.is_dir():
        path.rmdir()
        return

    for child in path.iterdir():
        delete_path(child, recursive)

    path.rmdir()


def mkdir(path: Path, recursive: bool = False) -> None:
    """Mkdir.

    Parameters
    ----------
    path : Path
        path parameter value.
    recursive : bool
        recursive parameter value.

    Returns
    -------
    None
        Computed return value."""
    if not path.parent.exists() and recursive:
        mkdir(path.parent, recursive=recursive)

    if path.exists():
        return

    os.mkdir(path)


def print_progress_async(msg: str):
    """
    Decorator to print a progress spinner with a given message while the function executes.

    Runs the Sprinner in an async function.

    Parameters
    ----------
    msg : `str`
        The message to show behind the spinner while the function runs.
    """

    def decorator_print_progress_async(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Callable:
            result = func(*args, **kwargs)

            if config.log_level in [
                opts.LogLevels.WARNING,
                opts.LogLevels.ERROR,
            ]:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                ) as progress:
                    progress.add_task(description=msg, total=None)
                    # time.sleep(3)

            return await result

        return wrapper

    return decorator_print_progress_async


def get_logger(func):
    """
    Descorator to refresh the logger object within a package, otherwise
    settings like log level are not updated based on cli input.

    Parameters
    ----------
    func : `Callable`
        The function to decorate.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Callable[..., Any]:
        start_logger(func.__module__)
        return func(*args, **kwargs)

    return wrapper


def start_logger(
    log_name: str = "template log",
    log_directory: str = f"{Path(__file__).parents[1]}\\Logs",
    enable_write_log: bool = False,
) -> logging.Logger:
    """Initialize and configure a logger.

    Parameters
    ----------
    log_name : `str`, optional
        Name of the logger. Defaults to "template log".
    log_directory : `str`, optional
        Directory to store log files. Defaults to f"{Path(__file__).parents[1]}\\Logs".
    enable_write_log : `bool`, optional
        Enable writing logs to file. Defaults to False.
    log_level : `logging.log`, optional
        Logging level. Defaults to logging.INFO.

    Returns
    -------
    logging.Logger
        Initialized logger object.
    """
    log_path = f"{log_directory}\\{log_name}.log"

    logger = logging.getLogger(log_name)
    logger.setLevel(config.log_level.value.upper())

    if enable_write_log and not logger.hasHandlers():
        # Create Log
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        # Remove Old Log file
        if os.path.exists(log_path):
            os.remove(log_path)

        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s: %(message)s"
        )
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    # Adding Stream handler to print out logs additionally to the console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColorFormatter())

    if not logger.hasHandlers():
        logger.addHandler(stream_handler)

    return logger


class ColorFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning/errors"""

    grey = "\x1b[90m"
    green = "\x1b[92m"
    yellow = "\x1b[93m"
    red = "\x1b[91m"
    reset = "\x1b[0m"
    _time = grey + "%(asctime)s "
    _level = "[%(levelname)-5s] "
    _scope = grey + "%(name)s | "
    _msg = "%(message)s" + reset

    # fmt: off
    FORMATS = {
        logging.DEBUG:    _time          + _level + _scope + reset + _msg,
        logging.INFO:     _time + green  + _level + _scope + reset + _msg,
        logging.WARNING:  _time + yellow + _level + _scope + reset + _msg,
        logging.ERROR:    _time + red    + _level + _scope + red   + _msg,
        logging.CRITICAL: _time + red    + _level + _scope + red   + _msg,
    }
    # fmt: on

    def format(self, record) -> str:
        record.levelname = "WARN" if record.levelname == "WARNING" else record.levelname
        record.levelname = "ERROR" if record.levelname == "CRITICAL" else record.levelname
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
