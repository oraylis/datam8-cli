from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import click
import typer

from datam8.cli.output import emit_error_json, emit_human, emit_json
from datam8.core.connectors.builtins import register_builtin_connectors
from datam8.core.connectors.registry import connector_registry
from datam8.core.connectors.resolve import resolve_and_validate
from datam8.core.duration import parse_duration_seconds
from datam8.core.entity_resolution import resolve_model_entity
from datam8.core.errors import Datam8Error, Datam8NotImplementedError, as_datam8_error
from datam8.core.errors import Datam8ValidationError
from datam8.core.indexing import read_index, validate_index
from datam8.core.jsonops import merge_patch, set_by_pointer
from datam8.core.lock import SolutionLock
from datam8.core.plugins.manager import (
    default_plugin_dir,
    install_git_url as plugins_install_git_url,
    install_zip as plugins_install_zip,
    reload as plugins_reload,
    set_enabled as plugins_set_enabled,
    uninstall as plugins_uninstall,
    verify_zip_bundle as plugins_verify_zip_bundle,
)
from datam8.core.refactor import refactor_entity_id as core_refactor_entity_id
from datam8.core.refactor import refactor_keys as core_refactor_keys
from datam8.core.refactor import refactor_values as core_refactor_values
from datam8.core.search import search_entities as core_search_entities
from datam8.core.search import search_text as core_search_text
from datam8.core.secrets import (
    delete_runtime_secret,
    get_runtime_secret,
    get_runtime_secrets_map,
    is_keyring_available,
    list_runtime_secret_keys,
    set_runtime_secret,
)
from datam8.core.trace import new_trace_id
from datam8.core.version import get_version
from datam8.core.workspace_io import (
    create_model_entity,
    create_new_project,
    delete_base_entity,
    delete_function_source,
    delete_model_entity,
    duplicate_model_entity,
    list_base_entities,
    list_directory,
    list_function_sources,
    list_model_entities,
    move_model_entity,
    read_function_source,
    read_solution,
    read_workspace_json,
    regenerate_index,
    rename_folder,
    rename_function_source,
    refactor_properties,
    write_base_entity,
    write_function_source,
    write_model_entity,
)

from datam8.cmd import generate as generate_cmd
from datam8.cmd import reverse as reverse_cmd
from datam8.cmd import serve as serve_cmd
from datam8.cmd import validate as validate_cmd


@dataclass(frozen=True)
class GlobalOptions:
    solution: Optional[str]
    json: bool
    quiet: bool
    verbose: bool
    log_file: Optional[str]
    lock_timeout: str
    no_lock: bool


app = typer.Typer(add_completion=False, no_args_is_help=True)

solution_app = typer.Typer(name="solution", add_completion=False, no_args_is_help=True)
base_app = typer.Typer(name="base", add_completion=False, no_args_is_help=True)
model_app = typer.Typer(name="model", add_completion=False, no_args_is_help=True)
script_app = typer.Typer(name="script", add_completion=False, no_args_is_help=True)
index_app = typer.Typer(name="index", add_completion=False, no_args_is_help=True)
refactor_app = typer.Typer(name="refactor", add_completion=False, no_args_is_help=True)
search_app = typer.Typer(name="search", add_completion=False, no_args_is_help=True)
connector_app = typer.Typer(name="connector", add_completion=False, no_args_is_help=True)
secret_app = typer.Typer(name="secret", add_completion=False, no_args_is_help=True)
plugin_app = typer.Typer(name="plugin", add_completion=False, no_args_is_help=True)
diag_app = typer.Typer(name="diag", add_completion=False, no_args_is_help=True)

app.add_typer(solution_app)
app.add_typer(base_app)
app.add_typer(model_app)
app.add_typer(script_app)
app.add_typer(index_app)
app.add_typer(refactor_app)
app.add_typer(search_app)
app.add_typer(connector_app)
app.add_typer(secret_app)
app.add_typer(plugin_app)
app.add_typer(diag_app)

# Keep existing commands as top-level commands for compatibility.
app.add_typer(generate_cmd.app)
app.add_typer(validate_cmd.app)
app.add_typer(reverse_cmd.app)
app.add_typer(serve_cmd.app)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(get_version())
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    ctx: typer.Context,
    solution: Optional[str] = typer.Option(
        None,
        "--solution",
        help="Path to .dm8s file (or folder containing it). Defaults to DATAM8_SOLUTION_PATH.",
    ),
    json: bool = typer.Option(False, "--json", help="Output JSON only to stdout (no extra text)."),
    quiet: bool = typer.Option(False, "--quiet", help="Minimal output."),
    verbose: bool = typer.Option(False, "--verbose", help="More logs (redacted)."),
    log_file: Optional[str] = typer.Option(None, "--log-file", help="Structured logs to file."),
    lock_timeout: str = typer.Option("10s", "--lock-timeout", help="Solution lock timeout (e.g. 10s, 2m)."),
    no_lock: bool = typer.Option(False, "--no-lock", help="Disable solution lock (dangerous)."),
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    ctx.obj = GlobalOptions(
        solution=solution or os.environ.get("DATAM8_SOLUTION_PATH"),
        json=json,
        quiet=quiet,
        verbose=verbose,
        log_file=log_file,
        lock_timeout=lock_timeout,
        no_lock=no_lock,
    )


def _run_editor(*, suffix: str, initial_text: str) -> str:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        raise Datam8ValidationError(message="No editor configured.", details={"hint": "Set EDITOR or VISUAL."})

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=suffix, newline="\n") as f:
        f.write(initial_text)
        tmp = f.name
    try:
        subprocess.check_call([editor, tmp])
        return Path(tmp).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _lock_if_needed(opts: GlobalOptions, root_dir: Path):
    if opts.no_lock:
        return None
    return SolutionLock(root_dir / ".datam8.lock", timeout_seconds=parse_duration_seconds(opts.lock_timeout))


def _ensure_connectors_loaded() -> None:
    register_builtin_connectors()


@solution_app.command("info")
def solution_info(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, sol = read_solution(opts.solution)
    payload = {
        "status": "ok",
        "solutionPath": str(resolved.solution_file),
        "solution": sol.model_dump(),
        "resolvedPaths": {"base": sol.basePath, "model": sol.modelPath},
        "traceId": trace_id,
    }
    if opts.json:
        emit_json(payload)
    else:
        emit_human(f"solution: {resolved.solution_file}")
        emit_human(f"schemaVersion: {sol.schemaVersion}")
        emit_human(f"basePath: {sol.basePath}")
        emit_human(f"modelPath: {sol.modelPath}")


@solution_app.command("full")
def solution_full(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, sol = read_solution(opts.solution)
    base_entities = [e.__dict__ for e in list_base_entities(opts.solution)]
    model_entities = [e.__dict__ for e in list_model_entities(opts.solution)]
    payload = {
        "status": "ok",
        "solutionPath": str(resolved.solution_file),
        "solution": sol.model_dump(),
        "baseEntities": base_entities,
        "modelEntities": model_entities,
        "traceId": trace_id,
    }
    if opts.json:
        emit_json(payload)
    else:
        emit_human(f"solution: {resolved.solution_file}")
        emit_human(f"baseEntities: {len(base_entities)}")
        emit_human(f"modelEntities: {len(model_entities)}")


@solution_app.command("validate")
def solution_validate(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    payload = {"status": "ok", "solutionPath": str(resolved.solution_file), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"ok: {resolved.solution_file}")


@solution_app.command("init")
def solution_init(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Solution/project name."),
    root: str = typer.Option(..., "--root", help="Directory where the project folder is created."),
    target: str = typer.Option(..., "--target", help="Generator target name (scaffolded only)."),
    base_path: Optional[str] = typer.Option(None, "--base-path", help="Base folder name (default: Base)."),
    model_path: Optional[str] = typer.Option(None, "--model-path", help="Model folder name (default: Model)."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    solution_path = create_new_project(
        name=name,
        root=root,
        target=target,
        base_path=base_path,
        model_path=model_path,
    )
    payload = {"status": "ok", "solutionPath": solution_path, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(solution_path)


@base_app.command("list")
def base_list(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ents = list_base_entities(opts.solution)
    payload = {"status": "ok", "count": len(ents), "baseEntities": [e.__dict__ for e in ents], "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for e in ents:
            emit_human(e.relPath)


@base_app.command("get")
def base_get(ctx: typer.Context, rel_path: str = typer.Argument(..., help="Path relative to solution root.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    content = read_workspace_json(rel_path, opts.solution)
    payload = {"status": "ok", "relPath": rel_path, "content": content, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(content, indent=2, ensure_ascii=False))


@base_app.command("save")
def base_save(ctx: typer.Context, rel_path: str = typer.Argument(...), content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    if content == "-":
        raw = sys.stdin.read()
    elif content.startswith("@"):
        raw = Path(content[1:]).read_text(encoding="utf-8")
    else:
        raw = content
    doc = json.loads(raw)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = write_base_entity(rel_path, doc, opts.solution)
    else:
        abs_path = write_base_entity(rel_path, doc, opts.solution)
    payload = {"status": "ok", "result": {"status": "saved", "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"saved: {abs_path}")


@base_app.command("delete")
def base_delete(ctx: typer.Context, rel_path: str = typer.Argument(...)) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = delete_base_entity(rel_path, opts.solution)
    else:
        abs_path = delete_base_entity(rel_path, opts.solution)
    payload = {"status": "ok", "result": {"status": "deleted", "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"deleted: {abs_path}")


@model_app.command("list")
def model_list(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ents = list_model_entities(opts.solution)
    payload = {"status": "ok", "count": len(ents), "modelEntities": [e.__dict__ for e in ents], "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for e in ents:
            emit_human(e.relPath)


@model_app.command("get")
def model_get(
    ctx: typer.Context,
    selector: str = typer.Argument(..., help="Entity selector (relPath, locator, id, or name)."),
    by: str = typer.Option("auto", "--by", help="Selector type: auto|relPath|locator|id|name."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(selector, solution_path=opts.solution, by=by)
    content = read_workspace_json(ent.rel_path, opts.solution)
    payload = {"status": "ok", "entity": ent.rel_path, "content": content, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(content, indent=2, ensure_ascii=False))


@model_app.command("create")
def model_create(
    ctx: typer.Context,
    rel_path: str = typer.Argument(..., help="New entity relPath (under Model/...)."),
    name: Optional[str] = typer.Option(None, "--name", help="Optional entity name."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = create_model_entity(rel_path, name=name, solution_path=opts.solution)
    else:
        abs_path = create_model_entity(rel_path, name=name, solution_path=opts.solution)
    payload = {"status": "ok", "result": {"status": "created", "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"created: {abs_path}")


@model_app.command("save")
def model_save(
    ctx: typer.Context,
    selector: str = typer.Argument(..., help="Entity selector (relPath, locator, id, or name)."),
    content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
    by: str = typer.Option("auto", "--by"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    if content == "-":
        raw = sys.stdin.read()
    elif content.startswith("@"):
        raw = Path(content[1:]).read_text(encoding="utf-8")
    else:
        raw = content
    doc = json.loads(raw)
    ent = resolve_model_entity(selector, solution_path=opts.solution, by=by)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = write_model_entity(ent.rel_path, doc, opts.solution)
    else:
        abs_path = write_model_entity(ent.rel_path, doc, opts.solution)
    payload = {"status": "ok", "result": {"status": "saved", "entity": ent.rel_path, "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"saved: {abs_path}")


@model_app.command("delete")
def model_delete(
    ctx: typer.Context,
    selector: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(selector, solution_path=opts.solution, by=by)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = delete_model_entity(ent.rel_path, opts.solution)
    else:
        abs_path = delete_model_entity(ent.rel_path, opts.solution)
    payload = {"status": "ok", "result": {"status": "deleted", "entity": ent.rel_path, "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"deleted: {abs_path}")


@model_app.command("move")
def model_move(
    ctx: typer.Context,
    from_rel_path: str = typer.Argument(...),
    to_rel_path: str = typer.Argument(...),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            result = move_model_entity(from_rel_path, to_rel_path, opts.solution)
    else:
        result = move_model_entity(from_rel_path, to_rel_path, opts.solution)
    payload = {"status": "ok", "result": {"status": "moved", **result, "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"moved: {result['fromAbsPath']} -> {result['toAbsPath']}")


@model_app.command("duplicate")
def model_duplicate(
    ctx: typer.Context,
    from_rel_path: str = typer.Argument(...),
    to_rel_path: str = typer.Argument(...),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            result = duplicate_model_entity(from_rel_path, to_rel_path, opts.solution)
    else:
        result = duplicate_model_entity(from_rel_path, to_rel_path, opts.solution)
    payload = {"status": "ok", "result": {"status": "duplicated", **result, "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"duplicated: {result['fromAbsPath']} -> {result['toAbsPath']}")


@model_app.command("folder-rename")
def model_folder_rename(
    ctx: typer.Context,
    from_folder_rel_path: str = typer.Argument(...),
    to_folder_rel_path: str = typer.Argument(...),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            result = rename_folder(from_folder_rel_path, to_folder_rel_path, opts.solution)
    else:
        result = rename_folder(from_folder_rel_path, to_folder_rel_path, opts.solution)
    payload = {"status": "ok", "result": {"status": "renamed", **result, "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@model_app.command("edit")
def model_edit(ctx: typer.Context, selector: str = typer.Argument(...), by: str = typer.Option("auto", "--by")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(selector, solution_path=opts.solution, by=by)
    current = read_workspace_json(ent.rel_path, opts.solution)
    edited_raw = _run_editor(suffix=".json", initial_text=json.dumps(current, indent=4, ensure_ascii=False) + "\n")
    try:
        next_doc = json.loads(edited_raw)
    except Exception as e:
        raise Datam8Error(code="validation_error", message="Edited JSON is invalid.", details={"error": str(e)}, exit_code=2)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = write_model_entity(ent.rel_path, next_doc, opts.solution)
    else:
        abs_path = write_model_entity(ent.rel_path, next_doc, opts.solution)
    payload = {"status": "ok", "result": {"status": "saved", "entity": ent.rel_path, "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"saved: {abs_path}")


@script_app.command("list")
def script_list(
    ctx: typer.Context,
    entity_selector: str = typer.Argument(..., help="Model entity selector owning the scripts."),
    by: str = typer.Option("auto", "--by"),
    entity_name: Optional[str] = typer.Option(None, "--entity-name", help="Optional entity name hint for folder resolution."),
    referenced_only: bool = typer.Option(False, "--referenced-only", help="Only list scripts referenced in transformations."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(entity_selector, solution_path=opts.solution, by=by)
    sources = list_function_sources(ent.rel_path, opts.solution, entity_name, include_unreferenced=not referenced_only)
    payload = {"status": "ok", "entity": ent.rel_path, "count": len(sources), "scripts": sources, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for s in sources:
            emit_human(s)


@script_app.command("get")
def script_get(
    ctx: typer.Context,
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: Optional[str] = typer.Option(None, "--entity-name"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(entity_selector, solution_path=opts.solution, by=by)
    content = read_function_source(ent.rel_path, source, opts.solution, entity_name)
    payload = {"status": "ok", "entity": ent.rel_path, "source": source, "content": content, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(content)


@script_app.command("save")
def script_save(
    ctx: typer.Context,
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    content: str = typer.Argument(..., help="Script content, @file, or '-' for stdin."),
    by: str = typer.Option("auto", "--by"),
    entity_name: Optional[str] = typer.Option(None, "--entity-name"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    if content == "-":
        script_content = sys.stdin.read()
    elif content.startswith("@"):
        script_content = Path(content[1:]).read_text(encoding="utf-8")
    else:
        script_content = content
    ent = resolve_model_entity(entity_selector, solution_path=opts.solution, by=by)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = write_function_source(ent.rel_path, source, script_content, opts.solution, entity_name)
    else:
        abs_path = write_function_source(ent.rel_path, source, script_content, opts.solution, entity_name)
    payload = {"status": "ok", "result": {"status": "saved", "source": source, "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"saved: {abs_path}")


@script_app.command("rename")
def script_rename(
    ctx: typer.Context,
    entity_selector: str = typer.Argument(...),
    from_source: str = typer.Argument(...),
    to_source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: Optional[str] = typer.Option(None, "--entity-name"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(entity_selector, solution_path=opts.solution, by=by)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            result = rename_function_source(ent.rel_path, from_source, to_source, opts.solution, entity_name)
    else:
        result = rename_function_source(ent.rel_path, from_source, to_source, opts.solution, entity_name)
    payload = {"status": "ok", "result": {"status": "renamed", **result, "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"renamed: {result['fromAbsPath']} -> {result['toAbsPath']}")


@script_app.command("delete")
def script_delete(
    ctx: typer.Context,
    entity_selector: str = typer.Argument(...),
    source: str = typer.Argument(...),
    by: str = typer.Option("auto", "--by"),
    entity_name: Optional[str] = typer.Option(None, "--entity-name"),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    ent = resolve_model_entity(entity_selector, solution_path=opts.solution, by=by)
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            abs_path = delete_function_source(ent.rel_path, source, opts.solution, entity_name)
    else:
        abs_path = delete_function_source(ent.rel_path, source, opts.solution, entity_name)
    payload = {"status": "ok", "result": {"status": "deleted", "source": source, "affectedFiles": [abs_path], "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"deleted: {abs_path}")


@index_app.command("regenerate")
def index_regenerate_cmd(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            index = regenerate_index(opts.solution)
    else:
        index = regenerate_index(opts.solution)
    payload = {"status": "ok", "result": {"status": "index_regenerated"}, "index": index, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("index regenerated")


@index_app.command("validate")
def index_validate_cmd(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    report = validate_index(opts.solution)
    payload = {"status": "ok" if report["ok"] else "error", "report": report, "traceId": trace_id}
    if not report["ok"]:
        emit_json(payload) if opts.json else emit_human("index validation failed")
        raise typer.Exit(code=2)
    emit_json(payload) if opts.json else emit_human("ok")


@index_app.command("read")
def index_read_cmd(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    idx = read_index(opts.solution)
    payload = {"status": "ok", "index": idx, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(idx, indent=2, ensure_ascii=False))


@refactor_app.command("properties")
def refactor_properties_cmd(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir)
    if lock:
        with lock:
            result = refactor_properties(opts.solution)
    else:
        result = refactor_properties(opts.solution)
    payload = {"status": "ok", "result": result, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@refactor_app.command("keys")
def refactor_keys_cmd(ctx: typer.Context, prefix: str = typer.Argument(...), replacement: str = typer.Argument(...), apply: bool = typer.Option(False, "--apply")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir) if apply else None
    if lock:
        with lock:
            result = core_refactor_keys(solution_path=opts.solution, prefix=prefix, replacement=replacement, apply=True)
    else:
        result = core_refactor_keys(solution_path=opts.solution, prefix=prefix, replacement=replacement, apply=apply)
    payload = {"status": "ok", "dryRun": not apply, "result": result, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})")


@refactor_app.command("values")
def refactor_values_cmd(ctx: typer.Context, prefix: str = typer.Argument(...), replacement: str = typer.Argument(...), apply: bool = typer.Option(False, "--apply")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir) if apply else None
    if lock:
        with lock:
            result = core_refactor_values(solution_path=opts.solution, prefix=prefix, replacement=replacement, apply=True)
    else:
        result = core_refactor_values(solution_path=opts.solution, prefix=prefix, replacement=replacement, apply=apply)
    payload = {"status": "ok", "dryRun": not apply, "result": result, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})")


@refactor_app.command("entity-id")
def refactor_entity_id_cmd(ctx: typer.Context, old: int = typer.Argument(...), new: int = typer.Argument(...), apply: bool = typer.Option(False, "--apply")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, _sol = read_solution(opts.solution)
    lock = _lock_if_needed(opts, resolved.root_dir) if apply else None
    if lock:
        with lock:
            result = core_refactor_entity_id(solution_path=opts.solution, old=old, new=new, apply=True)
    else:
        result = core_refactor_entity_id(solution_path=opts.solution, old=old, new=new, apply=apply)
    payload = {"status": "ok", "dryRun": not apply, "result": result, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(f"updatedFiles: {result['updatedFiles']} (dryRun={not apply})")


@search_app.command("entities")
def search_entities_cmd(ctx: typer.Context, query: str = typer.Argument(..., help="Substring query.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    result = core_search_entities(solution_path=opts.solution, query=query)
    payload = {"status": "ok", **result, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for e in result["entities"]:
            emit_human(e.get("relPath", ""))


@search_app.command("text")
def search_text_cmd(ctx: typer.Context, pattern: str = typer.Argument(..., help="Exact substring search.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    result = core_search_text(solution_path=opts.solution, pattern=pattern)
    payload = {"status": "ok", **result, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for m in result["matches"]:
            emit_human(f"{m['file']}: {m['count']}")


@connector_app.command("list")
def connector_list(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    _ensure_connectors_loaded()
    connectors = connector_registry.list()
    payload = {"status": "ok", "count": len(connectors), "connectors": connectors, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for c in connectors:
            emit_human(str((c.get("manifest") or {}).get("name")))


@connector_app.command("info")
def connector_info(ctx: typer.Context, id: str = typer.Argument(..., help="Connector id or alias.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    _ensure_connectors_loaded()
    mod = connector_registry.resolve_by_id(id) or connector_registry.resolve_by_alias(id)
    if not mod:
        raise Datam8Error(code="not_found", message="Connector not found.", details={"id": id}, exit_code=3)
    payload = {"status": "ok", "manifest": mod.manifest, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(mod.manifest, indent=2, ensure_ascii=False))


@connector_app.command("test")
def connector_test(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(..., help="DataSource name (Base/DataSources.json)."),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value (repeatable)."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    _ensure_connectors_loaded()
    overrides: dict[str, str] = {}
    for kv in secret or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            overrides[k.strip()] = v.strip()
    stored = get_runtime_secrets_map(solution_path=opts.solution, data_source_name=data_source_name, include_values=True)
    merged = {**stored, **overrides}
    module, manifest, cfg, secrets, _req = resolve_and_validate(solution_path=opts.solution, data_source_id=data_source_name, runtime_secrets=merged)
    connector = module.create_connector(cfg, secrets)
    if hasattr(connector, "list_tables"):
        _ = connector.list_tables()
    payload = {"status": "ok", "connector": manifest.get("name"), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@connector_app.command("browse")
def connector_browse(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(..., help="DataSource name (Base/DataSources.json)."),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value (repeatable)."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    _ensure_connectors_loaded()
    overrides: dict[str, str] = {}
    for kv in secret or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            overrides[k.strip()] = v.strip()
    stored = get_runtime_secrets_map(solution_path=opts.solution, data_source_name=data_source_name, include_values=True)
    merged = {**stored, **overrides}
    module, manifest, cfg, secrets, _req = resolve_and_validate(solution_path=opts.solution, data_source_id=data_source_name, runtime_secrets=merged)
    connector = module.create_connector(cfg, secrets)
    if not hasattr(connector, "list_tables"):
        raise Datam8Error(code="validation_error", message="Connector does not support browse.", details={"connector": manifest.get("name")}, exit_code=2)
    tables = connector.list_tables()
    payload = {"status": "ok", "tables": tables, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for t in tables:
            emit_human(f"{t.get('schema')}.{t.get('name')}")


@connector_app.command("fetch-metadata")
def connector_fetch_metadata(
    ctx: typer.Context,
    data_source_name: str = typer.Argument(..., help="DataSource name (Base/DataSources.json)."),
    schema: str = typer.Option("dbo", "--schema"),
    table: str = typer.Option(..., "--table"),
    secret: list[str] = typer.Option(None, "--secret", help="Override runtime secret as key=value (repeatable)."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    _ensure_connectors_loaded()
    overrides: dict[str, str] = {}
    for kv in secret or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            overrides[k.strip()] = v.strip()
    stored = get_runtime_secrets_map(solution_path=opts.solution, data_source_name=data_source_name, include_values=True)
    merged = {**stored, **overrides}
    module, manifest, cfg, secrets, _req = resolve_and_validate(solution_path=opts.solution, data_source_id=data_source_name, runtime_secrets=merged)
    connector = module.create_connector(cfg, secrets)
    if not hasattr(connector, "get_table_metadata"):
        raise Datam8Error(code="validation_error", message="Connector does not support metadata.", details={"connector": manifest.get("name")}, exit_code=2)
    metadata = connector.get_table_metadata(schema=schema, table=table)
    payload = {"status": "ok", "metadata": metadata, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(metadata, indent=2, ensure_ascii=False))


@secret_app.command("available")
def secret_available(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    payload = {"status": "ok", "available": bool(is_keyring_available()), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok" if payload["available"] else "unavailable")


@secret_app.command("list")
def secret_list(ctx: typer.Context, data_source_name: str = typer.Argument(...)) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    entries = list_runtime_secret_keys(opts.solution, data_source_name)
    payload = {"status": "ok", "dataSourceName": data_source_name, "count": len(entries), "secrets": entries, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for e in entries:
            emit_human(f"{e.get('key')}")


@secret_app.command("get")
def secret_get(ctx: typer.Context, data_source_name: str = typer.Argument(...), key: str = typer.Argument(...)) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    value = get_runtime_secret(opts.solution, data_source_name, key)
    payload = {"status": "ok", "dataSourceName": data_source_name, "key": key, "value": value, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(value or "")


@secret_app.command("set")
def secret_set(ctx: typer.Context, data_source_name: str = typer.Argument(...), key: str = typer.Argument(...), value: str = typer.Argument(...)) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    if value == "-":
        value = sys.stdin.read().strip("\n")
    ref = set_runtime_secret(solution_path=opts.solution, data_source_name=data_source_name, key=key, value=value)
    payload = {"status": "ok", "result": {"status": "saved", "secretRef": ref.to_uri(), "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@secret_app.command("delete")
def secret_delete(ctx: typer.Context, data_source_name: str = typer.Argument(...), key: str = typer.Argument(...)) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    delete_runtime_secret(opts.solution, data_source_name, key)
    payload = {"status": "ok", "result": {"status": "deleted", "traceId": trace_id}, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@plugin_app.command("list")
def plugin_list(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    state = plugins_reload(pd)
    payload = {"status": "ok", "plugins": state.get("plugins", []), "errors": state.get("errors", {}), "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        for p in state.get("plugins", []):
            if isinstance(p, dict):
                emit_human(str(p.get("id") or p.get("name") or ""))


@plugin_app.command("install")
def plugin_install(ctx: typer.Context, url: str = typer.Argument(..., help="Git URL or local zip path.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    if url.lower().endswith(".zip") and Path(url).exists():
        data = Path(url).read_bytes()
        _entry = plugins_install_zip(plugin_dir=pd, zip_bytes=data, file_name=Path(url).name)
        state = plugins_reload(pd)
    else:
        _entry = plugins_install_git_url(plugin_dir=pd, git_url=url)
        state = plugins_reload(pd)
    payload = {"status": "ok", "result": {"status": "installed", "traceId": trace_id}, "plugins": state.get("plugins", []), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@plugin_app.command("uninstall")
def plugin_uninstall(ctx: typer.Context, id: str = typer.Argument(..., help="Plugin id.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    plugins_uninstall(pd, id)
    state = plugins_reload(pd)
    payload = {"status": "ok", "result": {"status": "uninstalled", "id": id, "traceId": trace_id}, "plugins": state.get("plugins", []), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@plugin_app.command("enable")
def plugin_enable(ctx: typer.Context, id: str = typer.Argument(..., help="Plugin id.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    plugins_set_enabled(pd, id, True)
    state = plugins_reload(pd)
    payload = {"status": "ok", "result": {"status": "enabled", "id": id, "traceId": trace_id}, "plugins": state.get("plugins", []), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@plugin_app.command("disable")
def plugin_disable(ctx: typer.Context, id: str = typer.Argument(..., help="Plugin id.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    plugins_set_enabled(pd, id, False)
    state = plugins_reload(pd)
    payload = {"status": "ok", "result": {"status": "disabled", "id": id, "traceId": trace_id}, "plugins": state.get("plugins", []), "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human("ok")


@plugin_app.command("info")
def plugin_info(ctx: typer.Context, id: str = typer.Argument(..., help="Plugin id.")) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    state = plugins_reload(pd)
    plugin = next((p for p in state.get("plugins", []) if isinstance(p, dict) and p.get("id") == id), None)
    if not plugin:
        raise Datam8Error(code="not_found", message="Plugin not found.", details={"id": id}, exit_code=3)
    payload = {"status": "ok", "plugin": plugin, "traceId": trace_id}
    emit_json(payload) if opts.json else emit_human(json.dumps(plugin, indent=2, ensure_ascii=False))


@plugin_app.command("verify")
def plugin_verify(
    ctx: typer.Context,
    id: str = typer.Argument("", help="Plugin id (or omit when using --file)."),
    file: str | None = typer.Option(None, "--file", help="Verify a plugin ZIP bundle without installing it."),
) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    pd = Path(os.environ.get("DATAM8_PLUGIN_DIR") or str(default_plugin_dir()))
    if file and file.strip():
        data = Path(file).read_bytes()
        desc = plugins_verify_zip_bundle(zip_bytes=data)
        payload = {"status": "ok", "verified": True, "bundle": desc.__dict__, "traceId": trace_id}
    else:
        if not id.strip():
            raise Datam8Error(code="validation_error", message="id is required (or use --file).", details=None, exit_code=2)
        state = plugins_reload(pd)
        plugin = next((p for p in state.get("plugins", []) if isinstance(p, dict) and p.get("id") == id), None)
        if not plugin:
            raise Datam8Error(code="not_found", message="Plugin not found.", details={"id": id}, exit_code=3)
        ok = "sha256" in plugin and "entry" in plugin
        payload = {"status": "ok" if ok else "error", "verified": ok, "plugin": plugin, "traceId": trace_id}
        if not ok:
            raise Datam8Error(code="validation_error", message="Plugin verification failed.", details={"id": id}, exit_code=2)
    emit_json(payload) if opts.json else emit_human("ok")


@diag_app.command("info")
def diag_info(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    payload = {"status": "ok", "version": get_version(), "python": sys.version.split()[0], "solution": opts.solution, "traceId": trace_id}
    if opts.json:
        emit_json(payload)
    else:
        emit_human(f"datam8: {payload['version']}")
        emit_human(f"python: {payload['python']}")
        emit_human(f"solution: {opts.solution or '<none>'}")


@diag_app.command("doctor")
def diag_doctor(ctx: typer.Context) -> None:
    opts: GlobalOptions = ctx.obj
    trace_id = new_trace_id()
    resolved, sol = read_solution(opts.solution)
    payload = {
        "status": "ok",
        "solutionPath": str(resolved.solution_file),
        "lockFile": str(resolved.root_dir / ".datam8.lock"),
        "basePath": sol.basePath,
        "modelPath": sol.modelPath,
        "traceId": trace_id,
    }
    emit_json(payload) if opts.json else emit_human("ok")


@diag_app.command("bundle")
def diag_bundle() -> None:
    raise Datam8NotImplementedError(message="Bundle diagnostics are not implemented.")


def main(argv: Optional[list[str]] = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    trace_id = new_trace_id()
    try:
        app(prog_name="datam8", args=argv, standalone_mode=False)
    except typer.Exit as e:
        raise SystemExit(e.exit_code)
    except click.ClickException as err:
        msg = err.format_message() if hasattr(err, "format_message") else str(err)
        e = Datam8Error(code="validation_error", message=msg or "Invalid command.", details=None, hint=None, exit_code=2)
        json_mode = "--json" in argv
        if json_mode:
            emit_error_json(code=e.code, message=e.message, details=e.details, hint=e.hint, trace_id=trace_id)
        else:
            emit_human(msg)
        raise SystemExit(2)
    except Exception as err:
        e = as_datam8_error(err)
        json_mode = "--json" in argv
        if json_mode:
            emit_error_json(code=e.code, message=e.message, details=e.details, hint=e.hint, trace_id=trace_id)
        else:
            emit_human(e.message)
        raise SystemExit(e.exit_code)
