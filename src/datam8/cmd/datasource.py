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

from typing import Any

import typer

from datam8 import opts as cli_opts
from datam8.core.connectors.resolve import resolve_and_validate
from datam8.core.errors import Datam8ValidationError
from datam8.core.secrets import get_runtime_secrets_map
from datam8.core.workspace_io import read_solution

from .common import (
    emit_result,
    lock_context,
    make_global_options,
    read_json_arg,
    resolve_solution_path,
)

_SCHEMA_REFRESH_IMPORT_ERROR: ModuleNotFoundError | None = None
_ImportedUsageRef: Any = None
try:
    from datam8.core.schema_refresh import (
        UsageRef as _ImportedUsageRef,
    )
    from datam8.core.schema_refresh import (
        apply_schema_changes,
        find_data_source_usages,
        preview_schema_changes,
    )
except ModuleNotFoundError as import_error:
    _SCHEMA_REFRESH_IMPORT_ERROR = import_error

app = typer.Typer(
    name="datasource",
    add_completion=False,
    no_args_is_help=True,
    help="Datasource metadata and external schema refresh operations.",
)


def _ensure_schema_refresh_dependencies() -> None:
    if _SCHEMA_REFRESH_IMPORT_ERROR is None:
        return
    raise Datam8ValidationError(
        message="Datasource commands require optional dependencies that are not installed.",
        details={"missingDependency": str(_SCHEMA_REFRESH_IMPORT_ERROR)},
    )


if _SCHEMA_REFRESH_IMPORT_ERROR is not None:
    def find_data_source_usages(
        solution_path: str | None,
        data_source_name: str,
    ) -> list[dict[str, Any]]:
        _ = solution_path
        _ = data_source_name
        _ensure_schema_refresh_dependencies()
        return []

    def preview_schema_changes(
        *,
        solution_path: str | None,
        usages: list[Any],
        runtime_secrets: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        _ = solution_path
        _ = usages
        _ = runtime_secrets
        _ensure_schema_refresh_dependencies()
        return []

    def apply_schema_changes(
        *,
        solution_path: str | None,
        diffs: list[dict[str, Any]],
        runtime_secrets: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        _ = solution_path
        _ = diffs
        _ = runtime_secrets
        _ensure_schema_refresh_dependencies()
        return []

    def _make_usage_ref(entity_rel_path: str, source_index: int) -> Any:
        _ = entity_rel_path
        _ = source_index
        _ensure_schema_refresh_dependencies()
        return None

else:

    def _make_usage_ref(entity_rel_path: str, source_index: int) -> Any:
        return _ImportedUsageRef(entity_rel_path=entity_rel_path, source_index=source_index)


def _runtime_secrets(
    *,
    solution_path: str | None,
    data_source_id: str,
    runtime_secrets_arg: str,
) -> dict[str, str]:
    overrides = read_json_arg(runtime_secrets_arg)
    parsed = overrides if isinstance(overrides, dict) else {}
    stored = get_runtime_secrets_map(
        solution_path=solution_path,
        data_source_name=data_source_id,
        include_values=True,
    )
    return {**stored, **parsed}


@app.command("list-tables")
def list_tables(
    data_source_id: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List tables for a datasource connector."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution = resolve_solution_path(opts)
    merged = _runtime_secrets(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets_arg=runtime_secrets,
    )
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "list_tables"):
        raise Datam8ValidationError(
            message=f"Connector '{manifest.get('id')}' does not support metadata operations.",
            details=None,
        )
    tables = connector_cls.list_tables(cfg, resolver)  # type: ignore[attr-defined]
    emit_result(
        opts,
        {"tables": tables},
        human_lines=[f"{t.get('schema')}.{t.get('name')}" for t in tables if isinstance(t, dict)],
    )


@app.command("table-metadata")
def table_metadata(
    data_source_id: str = typer.Argument(...),
    schema: str = typer.Option("dbo", "--schema"),
    table: str = typer.Option(..., "--table"),
    solution_path: cli_opts.SolutionPathOptional = None,
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Fetch table metadata for a datasource connector."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution = resolve_solution_path(opts)
    merged = _runtime_secrets(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets_arg=runtime_secrets,
    )
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets=merged,
    )
    if not hasattr(connector_cls, "get_table_metadata"):
        raise Datam8ValidationError(
            message=f"Connector '{manifest.get('id')}' does not support metadata operations.",
            details=None,
        )
    metadata = connector_cls.get_table_metadata(cfg, resolver, schema, table)  # type: ignore[attr-defined]
    emit_result(opts, {"metadata": metadata})


@app.command("virtual-table-metadata")
def virtual_table_metadata(
    data_source_id: str = typer.Argument(...),
    source_location: str = typer.Option(..., "--source-location"),
    solution_path: cli_opts.SolutionPathOptional = None,
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Fetch HTTP API virtual table metadata."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution = resolve_solution_path(opts)
    merged = _runtime_secrets(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets_arg=runtime_secrets,
    )
    connector_cls, manifest, cfg, resolver = resolve_and_validate(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets=merged,
    )
    if manifest.get("id") != "http-api":
        raise Datam8ValidationError(
            message="DataSource is not configured with an HTTP API connector.",
            details=None,
        )
    source_location = (source_location or "").strip()
    if not source_location:
        raise Datam8ValidationError(message="sourceLocation is required.", details=None)
    if hasattr(connector_cls, "get_virtual_table_metadata"):
        metadata = connector_cls.get_virtual_table_metadata(  # type: ignore[attr-defined]
            cfg,
            resolver,
            source_location,
        )
        emit_result(opts, {"metadata": metadata})
        return
    metadata = connector_cls.get_table_metadata(cfg, resolver, "api", source_location)  # type: ignore[attr-defined]
    emit_result(opts, {"metadata": metadata})


@app.command("usages")
def usages(
    data_source_id: str = typer.Argument(...),
    solution_path: cli_opts.SolutionPathOptional = None,
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """List model-source usages for a datasource."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution = resolve_solution_path(opts)
    usages_list = find_data_source_usages(active_solution, data_source_id)
    emit_result(opts, {"usages": usages_list})


@app.command("refresh-preview")
def refresh_preview(
    data_source_id: str = typer.Argument(...),
    usages: str = typer.Option("[]", "--usages", help="JSON list of usage objects."),
    solution_path: cli_opts.SolutionPathOptional = None,
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
) -> None:
    """Preview external schema changes for selected usages."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
    active_solution = resolve_solution_path(opts)
    merged = _runtime_secrets(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets_arg=runtime_secrets,
    )
    usage_objects = read_json_arg(usages)
    usage_refs: list[Any] = []
    for usage in usage_objects if isinstance(usage_objects, list) else []:
        if not isinstance(usage, dict):
            continue
        rel_path = usage.get("entityRelPath")
        source_index = usage.get("sourceIndex")
        if isinstance(rel_path, str) and isinstance(source_index, int):
            usage_refs.append(_make_usage_ref(entity_rel_path=rel_path, source_index=source_index))
    diffs = preview_schema_changes(
        solution_path=active_solution,
        usages=usage_refs,
        runtime_secrets=merged or None,
    )
    emit_result(opts, {"diffs": diffs})


@app.command("refresh-apply")
def refresh_apply(
    data_source_id: str = typer.Argument(...),
    diffs: str = typer.Option("[]", "--diffs", help="JSON list."),
    solution_path: cli_opts.SolutionPathOptional = None,
    runtime_secrets: str = typer.Option("{}", "--runtime-secrets", help="JSON object."),
    json_output: cli_opts.JsonOutput = False,
    quiet: cli_opts.Quiet = False,
    lock_timeout: cli_opts.LockTimeout = "10s",
    no_lock: cli_opts.NoLock = False,
) -> None:
    """Apply external schema changes to affected model entities."""
    _ensure_schema_refresh_dependencies()
    opts = make_global_options(
        solution=solution_path,
        json_output=json_output,
        quiet=quiet,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )
    active_solution = resolve_solution_path(opts)
    merged = _runtime_secrets(
        solution_path=active_solution,
        data_source_id=data_source_id,
        runtime_secrets_arg=runtime_secrets,
    )
    diffs_payload = read_json_arg(diffs)
    if not isinstance(diffs_payload, list):
        raise Datam8ValidationError(message="diffs must be a JSON list.", details=None)
    resolved, _ = read_solution(active_solution)
    with lock_context(opts=opts, lock_file_root=resolved.root_dir):
        updated_entities: list[dict[str, Any]] = apply_schema_changes(
            solution_path=active_solution,
            diffs=diffs_payload,
            runtime_secrets=merged or None,
        )
    emit_result(opts, {"updatedEntities": updated_entities}, human_lines=["ok"])
