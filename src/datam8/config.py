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

from . import opts

supported_model_versions = ("2.0.0",)

log_level: opts.LogLevels = opts.LogLevels.WARNING

solution_folder_path: Path
solution_path: Path

module_path: Path
template_path: Path
output_path: Path
target: str = "none"

lazy: bool = False
"""
If set to true only resolves references when entity is looked up
"""
