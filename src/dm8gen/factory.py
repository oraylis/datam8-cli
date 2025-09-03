import asyncio


from dm8gen import config, parser, utils

logger = utils.start_logger(__name__)


def create_model():
    model = asyncio.run(parser.parse_full_solution(config.solution_path))

    # TODO: reference resolution

    return model
