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
from pathlib import Path
from typing import Any

import typer

from datam8 import opts as cli_opts
from datam8.core.connectors.plugin_host import (
    discover_connectors,
    get_connector,
    load_ui_schema,
    validate_connection,
)
from datam8.core.connectors.plugin_manager import default_plugin_dir
from datam8.core.connectors.resolve import resolve_and_validate
from datam8.core.errors import Datam8ValidationError
from datam8.core.secrets import get_runtime_secrets_map

from .common import emit_result, make_global_options, read_json_arg, resolve_solution_path

app = typer.Typer(
    name="connector",
    add_completion=False,
    no_args_is_help=True,
    help="List connectors and validate connector-based data source connections.",
)


def _plugin_dir() -> Path:
    configured = os.environ.get("DATAM8_PLUGIN_DIR")
    if configured and configured.strip():
        return Path(configured)
    return default_plugin_dir()


def _parse_secret_overrides(secret: list[str] | None) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in secret or []:
        if "=" in item:
            key, value = item.split("=", 1)
            overrides[key.strip()] = value.strip()
    return overrides


@app.command("list")
def list_connectors(
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List available connector plugins."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    connectors, errors = discover_connectors(plugin_dir=_plugin_dir())
    payload = {
        "count": len(connectors),
        "connectors": [c.to_summary() for c in connectors],
        "errors": errors,
    }
    emit_result(opts, payload, human_lines=[c.id for c in connectors])


@app.command("ui-schema")
def ui_schema(
    connector_id: str = typer.Argument(..., help="Connector id."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Return the UI schema for a connector."""
    opts = make_global_options(json_output=json_output, quiet=quiet)
    plugin = get_connector(plugin_dir=_plugin_dir(), connector_id=connector_id)
    schema = load_ui_schema(plugin=plugin)
    payload = {"connectorId": plugin.id, "version": plugin.version, "schema": schema}
    emit_result(opts, payload)


@app.command("validate-connection")
def validate_connection_cmd(
    connector_id: str = typer.Argument(..., help="Connector id."),
    solution_path: cli_opts.SolutionPathOptional = None,
    extended_properties: str = typer.Option("{}", "--extended-properties", help="JSON object."),
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Validate connector settings for a data source configuration."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    plugin = get_connector(plugin_dir=_plugin_dir(), connector_id=connector_id)
    ext_props = read_json_arg(extended_properties)
    rt_secrets = read_json_arg(runtime_secrets)
    result = validate_connection(
        plugin=plugin,
        solution_path=resolve_solution_path(opts),
        extended_properties=ext_props if isinstance(ext_props, dict) else {},
        runtime_secret_overrides=rt_secrets if isinstance(rt_secrets, dict) else None,
    )
    emit_result(opts, result)


@app.command("test")
def test_data_source(
    data_source_name: str = typer.Argument(..., help="DataSource name from Base/DataSources.json."),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Resolve and test a data source connection."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    overrides = _parse_secret_overrides(secret)
    stored = get_runtime_secrets_map(
        solution_path=active_solution_path,
        data_source_name=data_source_name,
        include_values=True,
    )
    merged = {**stored, **overrides}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution_path,
        data_source_id=data_source_name,
        runtime_secrets=merged,
    )
    if hasattr(connector_cls, "test_connection"):
        connector_cls.test_connection(cfg, resolver)  # type: ignore[attr-defined]
    emit_result(opts, {"status": "ok", "connector": manifest.get("id")}, human_lines=["ok"])


@app.command("browse")
def browse_data_source(
    data_source_name: str = typer.Argument(..., help="DataSource name from Base/DataSources.json."),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List available tables/sources for a data source."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    overrides = _parse_secret_overrides(secret)
    stored = get_runtime_secrets_map(
        solution_path=active_solution_path,
        data_source_name=data_source_name,
        include_values=True,
    )
    merged = {**stored, **overrides}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution_path,
        data_source_id=data_source_name,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(
            message="Connector does not support metadata browse operations.",
            details={"connector": manifest.get("id")},
        )
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    emit_result(
        opts,
        {"tables": tables},
        human_lines=[f"{t.get('schema')}.{t.get('name')}" for t in tables if isinstance(t, dict)],
    )


@app.command("fetch-metadata")
def fetch_metadata(
    data_source_name: str = typer.Argument(..., help="DataSource name from Base/DataSources.json."),
    schema: str = typer.Option("dbo", "--schema"),
    table: str = typer.Option(..., "--table"),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value."),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Fetch table metadata using a data source connector."""
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution_path = resolve_solution_path(opts)
    overrides = _parse_secret_overrides(secret)
    stored = get_runtime_secrets_map(
        solution_path=active_solution_path,
        data_source_name=data_source_name,
        include_values=True,
    )
    merged = {**stored, **overrides}
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution_path,
        data_source_id=data_source_name,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "get_table_metadata"):
        raise Datam8ValidationError(
            message="Connector does not support metadata operations.",
            details={"connector": manifest.get("id")},
        )
    metadata: dict[str, Any] = connector_cls.get_table_metadata(  # type: ignore[attr-defined]
        cfg,
        resolver,
        schema,
        table,
    )
    emit_result(opts, {"metadata": metadata})
