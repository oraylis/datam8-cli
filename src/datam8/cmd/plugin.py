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

import os
from dataclasses import asdict
from pathlib import Path

import typer

from datam8 import opts as cli_opts
from datam8.core.connectors.plugin_manager import (
    default_plugin_dir,
    install_git_url,
    install_zip,
    reload,
    set_enabled,
    uninstall,
    verify_zip_bundle,
)
from datam8.core.errors import Datam8NotFoundError, Datam8ValidationError

from .common import emit_result, make_global_options

app = typer.Typer(
    name="plugin",
    add_completion=False,
    no_args_is_help=True,
    help="Install and manage connector plugins.",
)


def _plugin_dir() -> Path:
    configured = os.environ.get("DATAM8_PLUGIN_DIR")
    if configured and configured.strip():
        return Path(configured)
    return default_plugin_dir()


@app.command("list")
def list_plugins(
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List installed plugins."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    state = reload(_plugin_dir())
    payload = {"plugins": state.get("plugins", []), "errors": state.get("errors", {})}
    human_lines = [
        str(p.get("id") or p.get("name") or "")
        for p in state.get("plugins", [])
        if isinstance(p, dict)
    ]
    emit_result(opts, payload, human_lines=human_lines)


@app.command("reload")
def reload_plugins(
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Rescan plugin directory and return plugin state."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    state = reload(_plugin_dir())
    emit_result(opts, state, human_lines=["ok"])


@app.command("install")
def install(
    git_url: str | None = typer.Option(None, "--git-url", help="Git URL to install from."),
    zip_file: str | None = typer.Option(None, "--zip-file", help="Local plugin ZIP file path."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Install a plugin from Git URL or ZIP file."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    plugin_dir = _plugin_dir()
    if bool(git_url) == bool(zip_file):
        raise Datam8ValidationError(message="Provide exactly one of --git-url or --zip-file.", details=None)

    if zip_file:
        zip_path = Path(zip_file)
        data = zip_path.read_bytes()
        install_zip(plugin_dir=plugin_dir, zip_bytes=data, file_name=zip_path.name)
    else:
        install_git_url(plugin_dir=plugin_dir, git_url=str(git_url))

    state = reload(plugin_dir)
    emit_result(opts, state, human_lines=["ok"])


@app.command("uninstall")
def uninstall_plugin(
    plugin_id: str = typer.Argument(..., help="Plugin id."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Uninstall a plugin by id."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    plugin_dir = _plugin_dir()
    uninstall(plugin_dir, plugin_id)
    state = reload(plugin_dir)
    emit_result(opts, state, human_lines=["ok"])


@app.command("enable")
def enable_plugin(
    plugin_id: str = typer.Argument(..., help="Plugin id."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Enable a plugin by id."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    plugin_dir = _plugin_dir()
    set_enabled(plugin_dir, plugin_id, True)
    state = reload(plugin_dir)
    emit_result(opts, state, human_lines=["ok"])


@app.command("disable")
def disable_plugin(
    plugin_id: str = typer.Argument(..., help="Plugin id."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Disable a plugin by id."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    plugin_dir = _plugin_dir()
    set_enabled(plugin_dir, plugin_id, False)
    state = reload(plugin_dir)
    emit_result(opts, state, human_lines=["ok"])


@app.command("info")
def plugin_info(
    plugin_id: str = typer.Argument(..., help="Plugin id."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Return plugin metadata for a single plugin."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    state = reload(_plugin_dir())
    plugin = next(
        (
            p
            for p in state.get("plugins", [])
            if isinstance(p, dict) and p.get("id") == plugin_id
        ),
        None,
    )
    if not plugin:
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": plugin_id})
    emit_result(opts, {"plugin": plugin})


@app.command("verify")
def verify_plugin(
    plugin_id: str = typer.Argument("", help="Plugin id (omit when using --file)."),
    file: str | None = typer.Option(None, "--file", help="Plugin ZIP file path."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Verify plugin metadata or validate a ZIP plugin bundle."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    if file and file.strip():
        data = Path(file).read_bytes()
        bundle = verify_zip_bundle(zip_bytes=data)
        emit_result(opts, {"verified": True, "bundle": asdict(bundle)}, human_lines=["ok"])
        return

    if not plugin_id.strip():
        raise Datam8ValidationError(message="plugin_id is required (or use --file).", details=None)
    state = reload(_plugin_dir())
    plugin = next(
        (
            p
            for p in state.get("plugins", [])
            if isinstance(p, dict) and p.get("id") == plugin_id
        ),
        None,
    )
    if not plugin:
        raise Datam8NotFoundError(message="Plugin not found.", details={"id": plugin_id})
    verified = "sha256" in plugin and "entry" in plugin
    payload = {"verified": verified, "plugin": plugin}
    emit_result(opts, payload, human_lines=["ok" if verified else "invalid"])
    if not verified:
        raise typer.Exit(code=2)
