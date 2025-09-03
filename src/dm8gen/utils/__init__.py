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

import json
import logging
import os
import textwrap
import time
from pathlib import Path
from collections.abc import Callable

import jsonschema
from rich.progress import Progress, SpinnerColumn, TextColumn

from dm8gen import config, opts


def print_progress_async(func: Callable):
    async def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        if config.log_level in [opts.LogLevels.WARNING, opts.LogLevels.ERROR]:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                progress.add_task(description="Processing...", total=None)
                time.sleep(3)

        return await result

    return wrapper


def validate_json_schema(path_json: str, path_json_schema: str):
    """Validate a JSON file against a JSON schema.

    Args:
        path_json (str): Path to the JSON file.
        path_json_schema (str): Path to the JSON schema file.
    """
    with open(path_json, encoding="utf-8") as f:
        js = json.load(f)

    # Read schema
    with open(path_json_schema, encoding="utf-8-sig", errors="ignore") as f:
        js_schema = json.load(f, strict=False)

    jsonschema.validate(js, schema=js_schema)


def read_json(path: str):
    """Read JSON data from a file.

    Args:
        path (str): Path to the JSON file.

    Returns:
        dict: JSON data.
    """
    with open(path, encoding="utf-8") as f:
        try:
            __json = json.load(f)
        except Exception as e:
            raise JsonFileParseException(e, path)

    return __json


def coalesce(values: list):
    """
    Coalesce implementation to get first None value of a list
    """
    return next((v for v in values if v is not None), None)


def get_locator(
    entity_type: str, data_product: str, data_module: str, entity_name: str
) -> str:
    """Get locator string for an entity.

    Args:
        entity_type (str): Type of the entity.
        data_product (str): Data product name.
        data_module (str): Data module name.
        entity_name (str): Entity name.

    Returns:
        str: Locator string.
    """
    locator = f"/{entity_type}/{data_product}/{data_module}/{entity_name}"
    return locator


def get_logger(func: Callable):
    def wrapper(*args, **kwargs):
        start_logger(func.__module__)
        return func(*args, **kwargs)

    return wrapper


def start_logger(
    log_name: str = "template log",
    log_directory: str = f"{Path(__file__).parents[1]}\\Logs",
    enable_write_log: bool = False,
) -> logging.Logger:
    """Initialize and configure a logger.

    Args:
        log_name (str, optional): Name of the logger. Defaults to "template log".
        log_directory (str, optional): Directory to store log files. Defaults to f"{Path(__file__).parents[1]}\\Logs".
        enable_write_log (bool, optional): Enable writing logs to file. Defaults to False.
        log_level (logging.log, optional): Logging level. Defaults to logging.INFO.

    Returns:
        logging.Logger: Initialized logger object.
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
    _level = "[%(levelname)s] "
    _scope = grey + "%(name)s | "
    _msg = "%(message)s" + reset

    FORMATS = {
        logging.DEBUG: _time + _level + _scope + reset + _msg,
        logging.INFO: _time + green + _level + _scope + reset + _msg,
        logging.WARNING: _time + yellow + _level + _scope + reset + _msg,
        logging.ERROR: _time + red + _level + _scope + red + _msg,
        logging.CRITICAL: _time + red + _level + _scope + red + _msg,
    }

    def format(self, record) -> str:
        record.levelname = (
            "WARN" if record.levelname == "WARNING" else record.levelname
        )
        record.levelname = (
            "ERROR" if record.levelname == "CRITICAL" else record.levelname
        )
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class JsonFileParseException(Exception):
    def __init__(self, e: Exception, file: str):
        Exception.__init__(self, str(e))
        self.file = file
        self.inner_exception = e
        self.message = str(e)

    def __str__(self):
        return self.message + textwrap.dedent(
            f"""
            File:       {self.file}
            Error-Type: {type(self.inner_exception)}
            """
        )
