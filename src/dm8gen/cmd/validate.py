import sys

import rich
import typer
from pydantic_core import ValidationError

from .. import config, factory, model_exceptions, opts, utils, parser_exceptions

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
    logger = utils.start_logger(__name__)

    try:
        _ = factory.create_model()

        rich.print("Validation successfull")

    except ValidationError as err:
        logger.error(err)
        sys.exit(1)
    except parser_exceptions.ModelParseException as err:
        logger.error(err)
        sys.exit(1)
    except model_exceptions.EntityNotFoundError as err:
        logger.error(err)
        sys.exit(1)
    except model_exceptions.PropertiesNotResolvedError as err:
        logger.error(err)
        sys.exit(1)
