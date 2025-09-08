import sys

import rich
import typer

from .. import config, factory, opts, utils

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.command("validate")
def command(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
):
    """Validate solution model."""
    config.log_level = log_level
    config.solution_path = solution_path
    config.solution_folder_path = solution_path.parent.absolute()

    _ = factory.create_model()

    rich.print("Validation successfull")
