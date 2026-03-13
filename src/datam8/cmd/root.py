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

"""
This module contains CLI commands to interact with the model, e.g. listing, adding or deleting
entities.

*Subcommands*
- list
- show
"""

import sys

import typer

from datam8 import (
    config,
    factory,
    generate,
    logging,
    model,
    model_exceptions,
    opts,
    solution,
    utils,
)
from datam8.api import app as api_app

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="datam8",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=True,
    pretty_exceptions_short=False,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)
"App to interact with the model - used as the default/root app"


def __setup_model_for_cli(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel,
    version: opts.Version,
) -> model.Model:
    config.lazy = True
    common.main_callback(solution_path, log_level, version)

    return factory.create_model_or_exit()


@app.callback(invoke_without_command=True)
def _callback(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    if version:
        typer.echo(common.get_version())
        raise typer.Exit(code=0)


@app.command()
def list(
    solution_path: opts.SolutionPath,
    locator: opts.Locator = "modelEntities",
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
    json_output: opts.JsonOutput = False,
) -> None:
    """List model entities"""
    common.main_callback(solution_path, log_level, version)

    model = __setup_model_for_cli(solution_path, log_level, version)
    wrappers = model.get_entities(locator)

    if len(wrappers) == 0:
        utils.emit_result("No entities found for search locator")
        raise typer.Exit(1)

    utils.emit_result(
        f"{len(wrappers)} entities in total",
        *[str(wrapper.locator) for wrapper in wrappers],
        models=[wrapper.entity for wrapper in wrappers],
        json=json_output,
    )


@app.command()
def show(
    selector: opts.Selector,
    solution_path: opts.SolutionPath,
    by: opts.SelectBy = opts.Selectors.LOCATOR,
    json_output: opts.JsonOutput = False,
    version: opts.Version = False,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
) -> None:
    """Get and display a model entity"""
    common.main_callback(solution_path, log_level, version)

    _model = __setup_model_for_cli(solution_path, log_level, version)
    entity_wrapper = None

    try:
        entity_wrapper = _model.get_entity_by_selector(selector, by)
    except model_exceptions.EntityNotFoundError as err:
        typer.echo(err)
        suggestions = []

        if by == opts.Selectors.LOCATOR:
            parent_locator = model.Locator.from_path(selector).parent
            typer.echo(parent_locator)
            suggestions = _model.get_entities(parent_locator) if parent_locator is not None else []

        if len(suggestions) > 0:
            typer.echo(f"Did you mean one of these?: {[str(w.locator) for w in suggestions]}")
        sys.exit(1)
    except ValueError as err:
        typer.echo(err)
        sys.exit(1)

    utils.emit_result(
        f"File: {entity_wrapper.source_file}",
        "\nProperties:",
        *entity_wrapper.properties.values(),
        "\nRaw Data:",
        entity_wrapper.entity,
        models=[entity_wrapper.entity],
        json=json_output,
        pretty=True,
    )


@app.command()
def validate(
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    """Validate solution model"""
    common.main_callback(solution_path, log_level, version)

    factory.create_model_or_exit(
        solution_path=config.solution_path,
    )

    typer.echo("Validation successfull")


@app.command(name="generate")
def generate_cmd(
    solution_path: opts.SolutionPath,
    target: opts.GeneratorTarget = opts.default_target,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    clean_output: opts.CleanOutput = False,
    payloads: opts.Payload = [],
    generate_all: opts.AllTargets = False,
    lazy: opts.Lazy = False,
    version: opts.Version = False,
):
    """Generate a jinja2 template configured in the solution file"""
    common.main_callback(solution_path, log_level, version)
    config.lazy = lazy

    if generate_all:
        logger.warning("The --all option is set, but is currently ignored.")

    model = factory.create_model_or_exit(config.solution_path)
    _ = generate.generate_output(
        model,
        target=target,
        payloads=payloads,
        generate_all=generate_all,
        clean_output=clean_output,
    )

    typer.echo("Generation successfull")


@app.command()
def init(
    name: opts.SolutionName,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
):
    """Initialise a new DataM8 solution"""
    common.main_callback(solution_path, log_level, version)

    new_solution_path = solution_path.resolve()
    if solution_path.suffix != ".dm8s":
        new_solution_path = new_solution_path / f"{name}.dm8s"

    if new_solution_path.exists():
        logger.error("Solution file aready exists at %s", new_solution_path)
        sys.exit(1)

    solution.init_solution(new_solution_path)

    typer.echo("Initialisation successfull")


@app.command()
def serve(
    solution_path: opts.SolutionPath,
    token: opts.ApiToken = None,
    host: opts.ApiHost = "127.0.0.1",
    port: opts.ApiPort = 0,
    openapi: opts.OpenApi = False,
    log_level: opts.LogLevel = opts.LogLevels.INFO,
    version: opts.Version = False,
):
    "Starts the DataM8 fastapi backend"
    config.run_as_api = True
    common.main_callback(solution_path, log_level, version)

    _ = factory.create_model()

    sock, actual_port = api_app._bind(host, port)
    server = api_app.create_server(
        host,
        actual_port,
        token=token.strip() if token is not None else token,
        enable_openapi=openapi,
    )
    server.run(sockets=[sock])


# TODO: everything below should get adapted in some way, because nobody wants to type json in the cli
# and commands like move are not necessary for the cli, as the whole model is simply dependent on the
# directories. would only be interesting to move a whole branch of the model tree


# @app.command("create")
# def create_entity(
#     rel_path: str = typer.Argument(..., help="New entity relPath under Model/."),
#     name: str | None = typer.Option(None, "--name", help="Optional entity name."),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Create a new model entity JSON file."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     abs_path = workspace_service.create_model_entity(
#         rel_path=rel_path,
#         name=name,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "created", "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"created: {abs_path}"])
#
#
# @app.command("save")
# def save_entity(
#     selector: str = typer.Argument(..., help="Entity selector (relPath, locator, id, or name)."),
#     content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
#     by: str = typer.Option("auto", "--by"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Overwrite a model entity JSON file."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     doc = read_json_arg(content)
#     abs_path = workspace_service.save_model_entity(
#         rel_path=entity.rel_path,
#         content=doc,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
#
#
# @app.command("validate")
# def validate_entity(
#     selector: str = typer.Argument(...),
#     by: str = typer.Option("auto", "--by"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
# ) -> None:
#     """Validate that a model entity matches the schema."""
#     opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     content = read_workspace_json(entity.rel_path, active_solution_path)
#     try:
#         model_model.ModelEntity.model_validate(content)
#     except ValidationError as e:
#         raise Datam8ValidationError(
#             message="Model entity validation failed.",
#             details={"relPath": entity.rel_path, "errors": e.errors()},
#         )
#     emit_result(
#         opts,
#         {"status": "ok", "relPath": entity.rel_path},
#         human_lines=[f"ok: {entity.rel_path}"],
#     )
#
#
# @app.command("set")
# def set_pointer(
#     selector: str = typer.Argument(...),
#     pointer: str = typer.Argument(...),
#     value_json: str = typer.Argument(...),
#     by: str = typer.Option("auto", "--by"),
#     create_missing: bool = typer.Option(True, "--create-missing/--no-create-missing"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Set a JSON pointer value inside a model entity and save it."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     current = read_workspace_json(entity.rel_path, active_solution_path)
#     value = read_json_arg(value_json)
#     next_doc = set_by_pointer(current, pointer, value, create_missing=create_missing)
#     abs_path = workspace_service.save_model_entity(
#         rel_path=entity.rel_path,
#         content=next_doc,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
#
#
# @app.command("patch")
# def patch_entity(
#     selector: str = typer.Argument(...),
#     patch_json: str = typer.Argument(...),
#     by: str = typer.Option("auto", "--by"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Apply JSON merge-patch to a model entity and save it."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     current = read_workspace_json(entity.rel_path, active_solution_path)
#     patch = read_json_arg(patch_json)
#     next_doc = merge_patch(current, patch)
#     abs_path = workspace_service.save_model_entity(
#         rel_path=entity.rel_path,
#         content=next_doc,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
#
#
# @app.command("delete")
# def delete_entity(
#     selector: str = typer.Argument(...),
#     by: str = typer.Option("auto", "--by"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Delete a model entity JSON file."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     abs_path = workspace_service.delete_model_entity(
#         rel_path=entity.rel_path,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "deleted", "entity": entity.rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])
#
#
# @app.command("move")
# def move_entity(
#     from_rel_path: str = typer.Argument(...),
#     to_rel_path: str = typer.Argument(...),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Move or rename a model entity path."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     result = workspace_service.move_model_entity(
#         from_rel_path=from_rel_path,
#         to_rel_path=to_rel_path,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "moved", **result.model_dump()}
#     emit_result(
#         opts,
#         payload,
#         human_lines=[f"moved: {result.fromAbsPath} -> {result.toAbsPath}"],
#     )
#
#
# @app.command("duplicate")
# def duplicate_entity(
#     from_rel_path: str = typer.Argument(...),
#     to_rel_path: str = typer.Argument(...),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Duplicate a model entity JSON file."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     result = workspace_service.duplicate_model_entity(
#         from_rel_path=from_rel_path,
#         to_rel_path=to_rel_path,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "duplicated", **result.model_dump()}
#     emit_result(
#         opts,
#         payload,
#         human_lines=[f"duplicated: {result.fromAbsPath} -> {result.toAbsPath}"],
#     )
#
#
# @app.command("folder-rename")
# def rename_model_folder(
#     from_folder_rel_path: str = typer.Argument(...),
#     to_folder_rel_path: str = typer.Argument(...),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Rename a model folder path and regenerate index."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     result = workspace_service.rename_model_folder(
#         from_folder_rel_path=from_folder_rel_path,
#         to_folder_rel_path=to_folder_rel_path,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {
#         "status": "renamed",
#         "fromAbsPath": result.fromAbsPath,
#         "toAbsPath": result.toAbsPath,
#         "entities": [entity.model_dump(mode="json") for entity in result.entities],
#         "index": result.index,
#     }
#     emit_result(
#         opts,
#         payload,
#         human_lines=[
#             f"renamed: {result.fromAbsPath} -> {result.toAbsPath}",
#             f"modelEntities: {len(result.entities)}",
#         ],
#     )
#
#
# @folder_metadata_app.command("get")
# def get_folder_metadata(
#     rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
# ) -> None:
#     """Read a folder metadata JSON document."""
#     opts = make_global_options(solution=solution_path, json_output=json_output, quiet=quiet)
#     active_solution_path = resolve_solution_path(opts)
#     content = workspace_service.read_folder_metadata(
#         rel_path=rel_path,
#         solution_path=active_solution_path,
#     )
#     content_payload = content.model_dump(mode="json")
#     payload = {"relPath": rel_path, "content": content_payload}
#     emit_result(
#         opts,
#         payload,
#         human_lines=[json.dumps(content_payload, indent=2, ensure_ascii=False)],
#     )
#
#
# @folder_metadata_app.command("save")
# def save_folder_metadata_cmd(
#     rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
#     content: str = typer.Argument(..., help="JSON string, @file, or '-' for stdin."),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Write a folder metadata JSON document."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     doc = read_json_arg(content)
#     abs_path = workspace_service.save_folder_metadata(
#         rel_path=rel_path,
#         content=doc,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "saved", "relPath": rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
#
#
# @folder_metadata_app.command("delete")
# def delete_folder_metadata_cmd(
#     rel_path: str = typer.Argument(..., help="Folder metadata relPath (*.properties.json)."),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Delete a folder metadata JSON document."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     abs_path = workspace_service.delete_folder_metadata(
#         rel_path=rel_path,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "deleted", "relPath": rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"deleted: {abs_path}"])
#
#
# @app.command("edit")
# def edit_entity(
#     selector: str = typer.Argument(...),
#     by: str = typer.Option("auto", "--by"),
#     solution_path: opts.SolutionPathOptional = None,
#     json_output: opts.JsonOutput = False,
#     quiet: opts.Quiet = False,
#     lock_timeout: opts.LockTimeout = "10s",
#     no_lock: opts.NoLock = False,
# ) -> None:
#     """Open a model entity JSON in $EDITOR and save it."""
#     opts = make_global_options(
#         solution=solution_path,
#         json_output=json_output,
#         quiet=quiet,
#         lock_timeout=lock_timeout,
#         no_lock=no_lock,
#     )
#     active_solution_path = resolve_solution_path(opts)
#     entity = resolve_model_entity(selector, solution_path=active_solution_path, by=by)
#     current = read_workspace_json(entity.rel_path, active_solution_path)
#     edited_raw = open_in_editor(
#         suffix=".json",
#         initial_text=json.dumps(current, indent=4, ensure_ascii=False) + "\n",
#     )
#     next_doc = json.loads(edited_raw)
#     abs_path = workspace_service.save_model_entity(
#         rel_path=entity.rel_path,
#         content=next_doc,
#         solution_path=active_solution_path,
#         no_lock=opts.no_lock,
#         lock_timeout=opts.lock_timeout,
#     )
#     payload = {"status": "saved", "entity": entity.rel_path, "absPath": abs_path}
#     emit_result(opts, payload, human_lines=[f"saved: {abs_path}"])
