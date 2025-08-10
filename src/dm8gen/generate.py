import json
from typing import Optional, Annotated
from enum import Enum
import typer
from .Factory.Jinja2Factory import Jinja2Factory
from .Factory.Model import Model
from .Generated.Solution import Model as Solution
from .Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class GenerateOptionEnum(str, Enum):
    """
    Enum class for defining different actions that the tool can perform.

    Attributes:
        VALIDATE_INDEX: Action to validate the index.
        GENERATE_TEMPLATE: Action to generate templates.
        REFRESH_GENERATE: Action to refresh and generate templates.
        REVERSE_GENERATE: Action to reverse generate staging entities from data sources.
    """

    VALIDATE_INDEX = "validate_index"
    GENERATE_TEMPLATE = "generate_template"
    REFRESH_GENERATE = "refresh_generate"
    REVERSE_GENERATE = "reverse_generate"


def generate(
    action: Annotated[
        GenerateOptionEnum,
        typer.Option(
            "--action",
            "-a",
            help="Choose the action for the tool.",
            case_sensitive=False,
        ),
    ],
    path_solution: Annotated[
        str,
        typer.Option(
            "--path-solution", "-s", help="File path to the solution JSON file."
        ),
    ],
    path_template_source: Annotated[
        Optional[str],
        typer.Option(
            "--path-template-source",
            "-src",
            help="Directory or file path to the template(s) source.",
        ),
    ] = None,
    path_template_destination: Annotated[
        Optional[str],
        typer.Option(
            "--path-template-destination",
            "-dest",
            help="Directory for template output.",
        ),
    ] = None,
    full_index_scan: Annotated[
        bool,
        typer.Option(
            "--full-index-scan",
            "-i",
            help="Flag to indicate a full index scan (True) or just a refresh (False).",
        ),
    ] = False,
    path_modules: Annotated[
        Optional[str],
        typer.Option(
            "--path-modules",
            "-m",
            help="Directory or file path to modules that can be registered.",
        ),
    ] = None,
    path_collections: Annotated[
        Optional[str],
        typer.Option(
            "--path-collections",
            "-c",
            help="Directory path to Jinja2 collections (templates for blocks and includes).",
        ),
    ] = None,
    # Reverse generate specific parameters
    data_source: Annotated[
        Optional[str],
        typer.Option(
            "--data-source",
            help="Name of the data source for reverse generation (required for reverse_generate).",
        ),
    ] = None,
    data_product: Annotated[
        Optional[str],
        typer.Option(
            "--data-product",
            help="Data product name for output path (required for reverse_generate).",
        ),
    ] = None,
    data_module: Annotated[
        Optional[str],
        typer.Option(
            "--data-module",
            help="Data module name for output path (required for reverse_generate).",
        ),
    ] = None,
    tables: Annotated[
        Optional[str],
        typer.Option(
            "--tables",
            help="Comma-separated list of table names to reverse generate (required for reverse_generate).",
        ),
    ] = None,
    entity_names: Annotated[
        Optional[str],
        typer.Option(
            "--entity-names",
            help="Comma-separated list of entity names corresponding to tables (optional for reverse_generate).",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            help="Enable interactive mode for reverse generation with user prompts.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Set log level: NOTSET, DEBUG, INFO, WARN, ERROR, CRITICAL (default INFO).",
        ),
    ] = "INFO",
):
    """
    Main function to execute different actions based on user input.

    Args:
        action (GenerateOptionEnum): The action to perform (validate_index, generate_template, refresh_generate, reverse_generate).
        path_solution (str): The file path to the solution JSON file.
        path_template_source (Optional[str]): The directory or file path to the template(s) source.
        path_template_destination (Optional[str]): The directory for template output.
        full_index_scan (bool): Flag to indicate whether to perform a full index scan or just refresh it.
        path_modules (Optional[str]): The directory or file path to modules that can be registered.
        path_collections (Optional[str]): The directory path to Jinja2 collections.
        data_source (Optional[str]): Name of the data source for reverse generation (required for reverse_generate).
        data_product (Optional[str]): Data product name for output path (required for reverse_generate).
        data_module (Optional[str]): Data module name for output path (required for reverse_generate).
        tables (Optional[str]): Comma-separated list of table names to reverse generate (required for reverse_generate).
        entity_names (Optional[str]): Comma-separated list of entity names corresponding to tables (optional for reverse_generate).
        interactive (bool): Enable interactive mode for reverse generation with user prompts.
        log_level (str): The log level for the application (default is "INFO").

    Raises:
        Exception: If the solution validation fails or an unknown action is provided.
    """
    # Validate Log level
    log_level_upper = log_level.upper()
    if not hasattr(logging, log_level_upper):
        log_level_int = logging.INFO
        logger = Helper.start_logger("main", log_level=logging.INFO)
        logger.warning(f"Invalid log level: {log_level} defaulting to INFO")
    else:
        log_level_int = getattr(logging, log_level_upper)
        Helper.start_logger("main", log_level=log_level_int)

    # Validate the provided solution file
    solution_data = Helper.read_json(path_solution)
    solution_object = Solution.model_validate_json(json.dumps(solution_data))

    missing_properties = [
        (attr, value)
        for attr, value in solution_object.__dict__.items()
        if value is None and attr != "name"
    ]

    if missing_properties:
        raise Exception(
            f"""
            Unable to read Solution File!
            --------------------------
            Missing Properties: {missing_properties}
            """
        )

    # Initialize the Model with the given solution path and log level
    model = Model(path_solution=path_solution, log_level=log_level_int)

    # Execute actions based on the provided action argument
    if action == GenerateOptionEnum.VALIDATE_INDEX:
        model.validate_index(full_index_scan=full_index_scan)
    elif action in {
        GenerateOptionEnum.GENERATE_TEMPLATE,
        GenerateOptionEnum.REFRESH_GENERATE,
    }:
        # Perform initial checks based on action type
        model.perform_initial_checks(
            "raw",
            *(
                ["stage", "core"]
                if action == GenerateOptionEnum.GENERATE_TEMPLATE
                else []
            ),
        )

        # If refreshing, validate index fully
        if action == GenerateOptionEnum.REFRESH_GENERATE:
            model.validate_index(full_index_scan=True)

        # Generate templates using Jinja2Factory
        jinja_factory = Jinja2Factory(model=model, log_level=log_level_int)
        jinja_factory.generate_template(
            path_template_source=path_template_source,
            path_template_destination=path_template_destination,
            path_modules=path_modules,
            path_collections=path_collections,
            path_solution=path_solution,
        )
    elif action == GenerateOptionEnum.REVERSE_GENERATE:
        # Import reverse generator components
        from .Factory.ReverseGenerator import ReverseGenerator
        
        # Parameter validation
        validation_errors = []
        
        # Check required parameters
        if not data_source:
            validation_errors.append("--data-source parameter is required for reverse_generate action")
        if not data_product:
            validation_errors.append("--data-product parameter is required for reverse_generate action")
        if not data_module:
            validation_errors.append("--data-module parameter is required for reverse_generate action")
        if not tables:
            validation_errors.append("--tables parameter is required for reverse_generate action")
        
        # Validate table/entity name count match
        if tables and entity_names:
            table_list = [t.strip() for t in tables.split(',')]
            entity_list = [e.strip() for e in entity_names.split(',')]
            
            if len(table_list) != len(entity_list):
                validation_errors.append(f"Number of entity names ({len(entity_list)}) must match number of tables ({len(table_list)})")
        
        if validation_errors:
            error_message = "Reverse generation parameter validation failed:\n" + "\n".join(validation_errors)
            raise Exception(error_message)
        
        # Parse comma-separated lists
        table_list = [t.strip() for t in tables.split(',')]
        entity_list = []
        if entity_names:
            entity_list = [e.strip() for e in entity_names.split(',')]
            if len(entity_list) != len(table_list):
                raise Exception("Number of entity names must match number of tables")
        
        # Create and execute reverse generator
        reverse_generator = ReverseGenerator(
            solution_path=path_solution,
            log_level=log_level_int
        )
        
        reverse_generator.generate_staging_entities(
            data_source_name=data_source,
            data_product=data_product,
            data_module=data_module,
            tables=table_list,
            entity_names=entity_list if entity_list else None,
            interactive=interactive
        )
    else:
        raise Exception(f"Unknown action: {action}")
