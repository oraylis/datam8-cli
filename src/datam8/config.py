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
from importlib.metadata import version
from pathlib import Path

from datam8 import opts
from datam8.core import errors

supported_model_versions: list[str] = [
    "2.0.0",
]

log_level: opts.LogLevels = opts.LogLevels.WARNING

solution_folder_path: Path = Path().cwd()
""" Path to the directory containing the dm8s file. Typically the repository's root """
solution_path: Path = Path().cwd()
""" Path to the dm8s file """
run_as_api: bool = False
"""
Flag to indicate weither datam8 runs in api mode. Some parts of the code will emit different
errors.
"""
lazy: bool = False
""" If set to true only resolves references when entity is looked up """


def latest_schema_version() -> str:
    return supported_model_versions[0]


def get_version() -> str:
    return version("datam8")


def set_solution(path: str | Path) -> None:
    """
    Configures the solution to be used within the library.

    Parameters
    ----------
    `path` : *str* or *Path*
        A pathlike object pointing to either a .dm8s file directory or a directory containing one. If a directory
        was provided it need to contain only a single .dm8s file.
    """
    global solution_path, solution_folder_path
    search_path = Path(path).expanduser()

    if search_path.is_file():
        solution_path = search_path.resolve(strict=True)
        solution_folder_path = solution_path.parent

    if search_path.is_dir():
        solution_folder_path = search_path
        dm8s_files = list(search_path.glob("*.dm8s"))

        match len(dm8s_files):
            case 1:
                solution_path = dm8s_files[0]
            case 0:
                raise errors.Datam8NotFoundError(
                    message="No .dm8s file found in the provided directory.",
                    details={"dir": search_path.as_posix()},
                )
            case _:
                raise errors.Datam8ValidationError(
                    message="Multiple .dm8s files found; provide an explicit .dm8s path.",
                    details={
                        "dir": {search_path.as_posix()},
                        "candidates": map(str, dm8s_files),
                    },
                )

    if not solution_path.exists():
        raise errors.Datam8NotFoundError(
            message="Solution file not found.",
            details={"solution": search_path.as_posix()},
        )
