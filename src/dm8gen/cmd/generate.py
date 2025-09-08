import asyncio
from concurrent import futures
import sys
import os

import rich
import typer

from dm8gen.model_exceptions import InvalidGeneratorTargetError
from dm8gen.utils.cache import Cache
from dm8model.solution import GeneratorTarget

from .. import config, factory, opts, utils, generate

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


@app.command("generate")
def command(
    solution_path: opts.SolutionPath,
    target: opts.GeneratorTarget = config.target,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    clean_output: opts.CleanOutput = False,
    payloads: opts.Payload = [],
):
    """Generate a jinja2 template configured in the solution file."""
    config.log_level = log_level
    config.solution_path = solution_path
    config.solution_folder_path = solution_path.parent.absolute()

    model = factory.create_model()
    cache = Cache()

    try:
        if target == "none":

            def filter_targets(_target: GeneratorTarget) -> bool:
                if _target.isDefault is None:
                    return False
                return _target.isDefault

            generator_target = [
                _t for _t in model.solution.generatorTargets if filter_targets(_t)
            ].pop()
        else:
            generator_target = model.get_generator_target(target)

        config.template_path = generator_target.sourcePath
        config.output_path = generator_target.outputPath
        output_path_abs = config.solution_folder_path / config.output_path
        module_path = (
            config.solution_folder_path / generator_target.sourcePath / "__modules"
        )

        _ = generate.load_modules(module_path)

        if clean_output and output_path_abs.exists():
            logger.warning("Cleaning Output...")
            utils.delete_path(output_path_abs, recursive=True)

        if not output_path_abs.exists():
            os.mkdir(output_path_abs)

        selected_payloads = {
            order: [
                payload
                for payload in generate.payload_functions[order]
                # NOTE: either payloads is set via cli arguments which results in
                # the first comparison to be truthy OR if no payload is set via
                # cli all payloads will be used due to the second condition being always true
                if payload.name in payloads or not payloads
            ]
            for order in sorted(generate.payload_functions)
        }

        for order in selected_payloads:
            executor = futures.ThreadPoolExecutor()

            def render_payload(
                payload: generate.PayloadDefinition,
            ) -> Exception | None:
                return asyncio.run(generate.render_payload(payload, model, cache))

            results = executor.map(
                render_payload,
                selected_payloads[order],
            )

            executor.shutdown()

            errors = [_result for _result in results if _result]

            if len(errors) > 0:
                raise generate.RenderError()

    except InvalidGeneratorTargetError as err:
        logger.error(err)
        sys.exit(1)
    except generate.RenderError as _:
        sys.exit(1)

    rich.print("Generation successfull")


#     # Validate Log level
#     log_level_upper = log_level.upper()
#     if not hasattr(logging, log_level_upper):
#         log_level_int = logging.INFO
#         logger = utils.start_logger("main", log_level=logging.INFO)
#         logger.warning(f"Invalid log level: {log_level} defaulting to INFO")
#     else:
#         log_level_int = getattr(logging, log_level_upper)
#         utils.start_logger("main", log_level=log_level_int)
#
#     # Validate the provided solution file
#     solution_data = utils.read_json(path_solution)
#     solution_object = Solution.model_validate_json(json.dumps(solution_data))
#
#     missing_properties = [
#         (attr, value)
#         for attr, value in solution_object.__dict__.items()
#         if value is None and attr != "name"
#     ]
#
#     if missing_properties:
#         raise Exception(
#             f"""
#             Unable to read Solution File!
#             --------------------------
#             Missing Properties: {missing_properties}
#             """
#         )


#     # Initialize the Model with the given solution path and log level
#     model = Model(path_solution=path_solution, log_level=log_level_int)
#
#     # Execute actions based on the provided action argument
#     if action == GenerateOptionEnum.VALIDATE_INDEX:
#         model.validate_index(full_index_scan=full_index_scan)
#     elif action in {
#         GenerateOptionEnum.GENERATE_TEMPLATE,
#         GenerateOptionEnum.REFRESH_GENERATE,
#     }:
#         # Perform initial checks based on action type
#         model.perform_initial_checks(
#             "raw",
#             *(
#                 ["stage", "core"]
#                 if action == GenerateOptionEnum.GENERATE_TEMPLATE
#                 else []
#             ),
#         )
#
#         # If refreshing, validate index fully
#         if action == GenerateOptionEnum.REFRESH_GENERATE:
#             model.validate_index(full_index_scan=True)
#
#         # Generate templates using Jinja2Factory
#         jinja_factory = Jinja2Factory(model=model, log_level=log_level_int)
#         jinja_factory.generate_template(
#             path_template_source=path_template_source,
#             path_template_destination=path_template_destination,
#             path_modules=path_modules,
#             path_collections=path_collections,
#             path_solution=path_solution,
#         )
#     elif action == GenerateOptionEnum.REVERSE_GENERATE:
#         # Import reverse generator components
#         from .Factory.ReverseGenerator import ReverseGenerator
#
#         # Parameter validation
#         validation_errors = []
#
#         # Check required parameters
#         if not data_source:
#             validation_errors.append(
#                 "--data-source parameter is required for reverse_generate action"
#             )
#         if not data_product:
#             validation_errors.append(
#                 "--data-product parameter is required for reverse_generate action"
#             )
#         if not data_module:
#             validation_errors.append(
#                 "--data-module parameter is required for reverse_generate action"
#             )
#         if not tables:
#             validation_errors.append(
#                 "--tables parameter is required for reverse_generate action"
#             )
#
#         # Validate table/entity name count match
#         if tables and entity_names:
#             table_list = [t.strip() for t in tables.split(",")]
#             entity_list = [e.strip() for e in entity_names.split(",")]
#
#             if len(table_list) != len(entity_list):
#                 validation_errors.append(
#                     f"Number of entity names ({len(entity_list)}) must match number of tables ({len(table_list)})"
#                 )
#
#         if validation_errors:
#             error_message = (
#                 "Reverse generation parameter validation failed:\n"
#                 + "\n".join(validation_errors)
#             )
#             raise Exception(error_message)
#
#         # Parse comma-separated lists
#         table_list = [t.strip() for t in tables.split(",")]
#         entity_list = []
#         if entity_names:
#             entity_list = [e.strip() for e in entity_names.split(",")]
#             if len(entity_list) != len(table_list):
#                 raise Exception(
#                     "Number of entity names must match number of tables"
#                 )
#
#         # Create and execute reverse generator
#         reverse_generator = ReverseGenerator(
#             solution_path=path_solution, log_level=log_level_int
#         )
#
#         reverse_generator.generate_staging_entities(
#             data_source_name=data_source,
#             data_product=data_product,
#             data_module=data_module,
#             tables=table_list,
#             entity_names=entity_list if entity_list else None,
#             interactive=interactive,
#         )
#     else:
#         raise Exception(f"Unknown action: {action}")
