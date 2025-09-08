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

import logging
import os
from collections.abc import Callable
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from .. import config, opts


def delete_path(path: Path, recursive: bool = False) -> None:
    if path.is_file():
        os.remove(path)
        return

    if not recursive and path.is_dir():
        path.rmdir()
        return

    for child in path.iterdir():
        delete_path(child, recursive)

    path.rmdir()


def print_progress_async(msg: str) -> Callable:
    """
    Decorator to print a progress spinner with a given message while the function executes.

    Runs the Sprinner in an async function.

    Parameters
    ----------
    msg : `str`
        The message to show behind the spinner while the function runs.
    """

    def decorator_print_progress_async(func: Callable) -> Callable:
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


def get_logger(func: Callable) -> Callable:
    """
    Descorator to refresh the logger object within a package, otherwise
    settings like log level are not updated based on cli input.

    Parameters
    ----------
    func : `Callable`
        The function to decorate.
    """

    def wrapper(*args, **kwargs) -> Callable:
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
