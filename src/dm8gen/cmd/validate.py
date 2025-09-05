import sys

from pydantic_core import ValidationError
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

        model_entity = model.get_model_entity_by_id(1001)
        rich.print("entity:", model_entity.locator)
        rich.print("properties:", model_entity.entity.properties)
        if model_entity.entity.properties:
            single_prop_ref = model_entity.entity.properties[0]
            rich.print(single_prop_ref)
            # rich.print(
            #     "property value:", model.get_property_values(single_prop_ref)
            # )

        # NOTE: Folder Tests
        # rich.print("folder:", model.folders)

        # NOTE: Property Values Tests
        # rich.print("solution:", model.solution)
        # rich.print("properties:", model.propertyValues)

        # NOTE: Data Source Tests
        # data_source = model.get_data_source("AdventureWorks")
        # rich.print("data source:", data_source.locator)
        # rich.print("data source:", data_source.entity.dataTypeMapping)

        # NOTE: Data Type Tests
        # data_type = model.get_data_type("string")
        # rich.print("data type:", data_type)
        # rich.print(
        #     "compare locator vs string:",
        #     data_type.locator == "dataTypes/string",
        # )

        # NOTE: Data Product Tests
        data_product = model.get_data_product("Sales")
        rich.print("data product:", data_product)
        rich.print(type(data_product))

        # NOTE: Data Module Tests
        data_module = model.get_data_module("Sales", "Customer")
        rich.print("data module:", data_module)

    except ValidationError as err:
        logger.error(err)
        sys.exit(1)
    except parser.ModelParseException as err:
        logger.error(err)
        sys.exit(1)
    except EntityNotFoundException as err:
        logger.error(err)
        sys.exit(1)
