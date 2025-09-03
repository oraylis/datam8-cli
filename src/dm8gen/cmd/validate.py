import sys

import typer
import rich

from dm8gen import config, factory, opts, parser, utils
from dm8gen.model import EntityNotFoundException

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
        model = factory.create_model()

        rich.print("solution:", model.solution)

        model_entity = model.get_model_entity_by_id(1001)
        rich.print("entity:", model_entity.locator)
        rich.print("property:", model_entity.get_property_value("write_mode", "merge"))

        data_source = model.get_data_source("AdventureWorks")
        rich.print("data source:", data_source.locator)
        rich.print("data source:", data_source.model_object.dataTypeMapping)

        data_type = model.get_data_type("string")
        rich.print("data type:", data_type)

        data_product = model.get_data_product("Sales")
        rich.print("data product:", data_product)

    except parser.ModelParseException as _:
        sys.exit(1)
    except EntityNotFoundException as err:
        logger.error(err)
        sys.exit(1)
