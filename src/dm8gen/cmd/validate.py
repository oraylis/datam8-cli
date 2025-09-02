import typer
import sys

from dm8gen import config, opts, parser, utils
from dm8gen.factory import EntityNotFoundException

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
    config.solution_folder_path = solution_path.parent.absolute()
    logger = utils.start_logger(__name__)
    logger.info("Start validating")

    try:
        parsed_model = parser.parse_full_solution(solution_path.absolute())
    except parser.ModelParseException as _:
        sys.exit(1)

    logger.info("Finished validating")

    try:
        test_entity = parsed_model.get_model_entity_by_id(1001)
        logger.info("entity: %s", test_entity.locator)
    except EntityNotFoundException as err:
        logger.error(err)
        sys.exit(1)


    """
    print("Start validating model entities")
    for model_file in model_path.glob("**/*.json"):
        if model_file.match(".properties.json"):
            continue

        rel_file_path = model_file.relative_to(
            solution_path.parent.absolute() / solution.modelPath
        )
        try:
            _ = ModelEntity.from_json_file(model_file)
            print("\t%s - Success" % rel_file_path)
        except ValidationError as e:
            errors[rel_file_path] = e
            print("\t%s - Error" % rel_file_path)

    if len(errors) == 0:
        print("\nno errors found")
    else:
        print("\nerrors found\n")
        for file, error in errors.items():
            print("%s\n%s" % (file, error))
    """
