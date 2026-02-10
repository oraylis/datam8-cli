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

import typer

from datam8.core.secrets import (
    delete_runtime_secret,
    get_runtime_secret,
    is_keyring_available,
    list_runtime_secret_keys,
    runtime_secret_ref,
    set_runtime_secret,
)

from .common import emit_result, get_global_options, read_text_arg, resolve_solution_path

app = typer.Typer(
    name="secret",
    add_completion=False,
    no_args_is_help=True,
    help="Manage runtime secrets.",
)


@app.command("available")
def available(ctx: typer.Context) -> None:
    """Return whether runtime secret storage is available."""
    opts = get_global_options(ctx)
    is_available = bool(is_keyring_available())
    emit_result(
        opts,
        {"available": is_available},
        human_lines=["ok" if is_available else "unavailable"],
    )


@app.command("list")
def list_keys(ctx: typer.Context, data_source_name: str = typer.Argument(...)) -> None:
    """List secret keys for a data source."""
    opts = get_global_options(ctx)
    entries = list_runtime_secret_keys(resolve_solution_path(opts), data_source_name)
    payload = {"dataSourceName": data_source_name, "count": len(entries), "secrets": entries}
    emit_result(opts, payload, human_lines=[str(e.get("key") or "") for e in entries])


@app.command("refs")
def refs(ctx: typer.Context, data_source_name: str = typer.Argument(...)) -> None:
    """List secret reference URIs for a data source."""
    opts = get_global_options(ctx)
    refs_map: dict[str, str] = {}
    for entry in list_runtime_secret_keys(resolve_solution_path(opts), data_source_name):
        key = entry.get("key")
        if isinstance(key, str) and key.strip():
            refs_map[key.strip()] = runtime_secret_ref(data_source_name=data_source_name, key=key.strip())
    emit_result(opts, {"runtimeSecrets": refs_map or None})


@app.command("get")
def get_secret(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
) -> None:
    """Read a runtime secret value."""
    opts = get_global_options(ctx)
    entry = get_runtime_secret(
        solution_path=resolve_solution_path(opts),
        data_source_name=data_source_name,
        key=key,
        reveal=True,
    )
    payload = {"dataSourceName": data_source_name, "key": key, "secret": entry}
    emit_result(opts, payload, human_lines=[str(entry.get("value") or "")])


@app.command("set")
def set_secret(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
    value: str = typer.Argument(..., help="Secret value or '-' for stdin."),
) -> None:
    """Create or update a runtime secret value."""
    opts = get_global_options(ctx)
    secret_value = read_text_arg(value).strip("\n")
    ref = set_runtime_secret(
        solution_path=resolve_solution_path(opts),
        data_source_name=data_source_name,
        key=key,
        value=secret_value,
    )
    emit_result(opts, {"status": "saved", "secretRef": ref.to_uri()}, human_lines=["ok"])


@app.command("delete")
def delete_secret(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(...),
    key: str = typer.Argument(...),
) -> None:
    """Delete a runtime secret value."""
    opts = get_global_options(ctx)
    delete_runtime_secret(
        solution_path=resolve_solution_path(opts),
        data_source_name=data_source_name,
        key=key,
    )
    emit_result(opts, {"status": "deleted"}, human_lines=["ok"])


@app.command("clear")
def clear_secrets(ctx: typer.Context, data_source_name: str = typer.Argument(...)) -> None:
    """Delete all runtime secrets for a data source."""
    opts = get_global_options(ctx)
    solution_path = resolve_solution_path(opts)
    for entry in list_runtime_secret_keys(solution_path, data_source_name):
        key = entry.get("key")
        if isinstance(key, str) and key.strip():
            try:
                delete_runtime_secret(
                    solution_path=solution_path,
                    data_source_name=data_source_name,
                    key=key,
                )
            except Exception:
                continue
    emit_result(opts, {"status": "cleared"}, human_lines=["ok"])
