from pathlib import Path

from . import opts


log_level: opts.LogLevels = opts.LogLevels.WARNING

solution_folder_path: Path
solution_path: Path

"""
If set to true only resolves references when entity is looked up
"""
lazy: bool = False
