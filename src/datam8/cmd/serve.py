# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#

# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import socket

import typer
import uvicorn

from datam8 import config, factory, logging, opts
from datam8.api.app import create_app

from . import common

app = typer.Typer(
    name="serve",
    add_completion=False,
    no_args_is_help=False,
    help="Starts the DataM8 fastapi backend.",
)

logger = logging.getLogger(__name__)


def _bind(host: str, port: int) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    actual_port = int(sock.getsockname()[1])
    return sock, actual_port


@app.callback(invoke_without_command=True)
def main(
    solution_path: opts.SolutionPath,
    token: opts.ApiToken = None,
    host: opts.ApiHost = "127.0.0.1",
    port: opts.ApiPort = 0,
    openapi: opts.OpenApi = False,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
):
    config.run_as_api = True
    common.main_callback(solution_path, log_level, version)

    model = factory.create_model()

    sock, actual_port = _bind(host, port)
    base_url = f"http://{host}:{actual_port}"

    if token is not None:
        api = create_app(token=token.strip(), enable_openapi=openapi)
    else:
        api = create_app(enable_openapi=openapi)

    @api.on_event("startup")
    async def _emit_ready() -> None:
        logger.info(
            f"API ready at `{base_url}`, schemaVersion: {model.solution.schemaVersion}"
        )

    server = uvicorn.Server(
        uvicorn.Config(
            api,
            host=host,
            port=actual_port,
            log_level=config.log_level.value,
            access_log=False,
        )
    )
    server.run(sockets=[sock])
