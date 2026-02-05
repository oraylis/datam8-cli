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

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import typer
import uvicorn

from datam8 import utils
from datam8.api.app import create_app
from datam8.core.jobs.manager import JobManager
from datam8.core.version import get_version

app = typer.Typer()

logger = utils.start_logger(__name__)
sys.tracebacklimit = 0


def _bind(host: str, port: int) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    actual_port = int(sock.getsockname()[1])
    return sock, actual_port


@app.command("serve")
def command(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(0, "--port", min=0, max=65535),
    token: str = typer.Option(..., "--token"),
    solution_path: Path | None = typer.Option(
        None,
        "--solution",
        "-s",
        "--solution-path",
        help="Path to .dm8s solution file (or folder containing it). Sets DATAM8_SOLUTION_PATH for the server process.",
        envvar="DATAM8_SOLUTION_PATH",
    ),
    openapi: bool = typer.Option(False, "--openapi"),
    log_level: str = typer.Option("info", "--log-level"),
):
    """Starts the DataM8 HTTP backend (desktop-safe)."""
    if not token or not token.strip():
        raise typer.BadParameter("--token is required.")
    if solution_path is None:
        parent_obj = getattr(ctx, "obj", None)
        candidate = getattr(parent_obj, "solution", None) if parent_obj is not None else None
        if isinstance(candidate, str) and candidate.strip():
            solution_path = Path(candidate)

    if solution_path is not None:
        os.environ["DATAM8_SOLUTION_PATH"] = str(solution_path)

    sock, actual_port = _bind(host, port)
    base_url = f"http://{host}:{actual_port}"

    jm = JobManager(max_concurrency=int(os.environ.get("DATAM8_JOB_CONCURRENCY") or "2"))
    api = create_app(token=token.strip(), enable_openapi=openapi, job_manager=jm)

    ready_payload = {"type": "ready", "baseUrl": base_url, "version": get_version()}
    ready_line = json.dumps(ready_payload, separators=(",", ":"))

    @api.on_event("startup")
    async def _emit_ready() -> None:
        await jm.start()
        sys.stdout.write(ready_line + "\n")
        sys.stdout.flush()

    @api.on_event("shutdown")
    async def _stop_jobs() -> None:
        await jm.stop()

    config = uvicorn.Config(
        api,
        host=host,
        port=actual_port,
        log_level=log_level,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run(sockets=[sock])
