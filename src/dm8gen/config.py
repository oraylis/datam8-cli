from pathlib import Path

from . import opts


log_level: opts.LogLevels = opts.LogLevels.WARNING

solution_folder_path: Path
solution_path: Path

template_path: Path
output_path: Path
target: str = "none"

lazy: bool = False
"""
If set to true only resolves references when entity is looked up
"""
