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


import rich
import typer
import deepdiff
from click import Choice

from datam8 import factory, logging, opts, source, utils

from . import common

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="sources",
    help="Subcommands to connect with and view sources",
    no_args_is_help=True,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)


@app.command("list")
def list_(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    source_location: opts.SourceLocation | None = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "List available objects in a source (schema, tables, etc.)"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    schemas = plugin.list_source(source_location)

    typer.echo(f"Found {len(schemas.rows())} source objects")
    schemas.show(None, tbl_hide_column_data_types=True, tbl_hide_dataframe_shape=True)


@app.command()
def preview(
    data_source_name: opts.DataSource,
    source_location: opts.SourceLocation,
    solution_path: opts.SolutionPath,
    limit: opts.Limit = 10,
    col_limit: opts.ColLimit = None,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Preview data from a source location"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    preview = plugin.preview_data(source_location, limit=limit)

    batches = preview.collect_batches(chunk_size=limit)

    # since the limit is pushed down to the source, there will be only one batch
    # batches are mostly used to safely get a dataframe from a LazyFrame
    df = next(batches)

    df.show(
        limit=limit,
        tbl_hide_dataframe_shape=True,
        tbl_cols=col_limit or len(preview.collect_schema().names()),
    )


@app.command("import")
def import_(
    data_source: opts.DataSource,
    source_location: opts.SourceLocation,
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Import a table from a source into the model at the provided locator"
    common.main_callback(solution_path, log_level, version)

    model_ = factory.get_model()

    if model_.has_locator(locator):
        raise utils.create_error("Entity already exists for this locator")

    _ = source.import_from_source(data_source, source_location, locator, model=model_)

    model_.save(locator)

    typer.echo(f"Source table imported into model at {locator}")


@app.command()
def refresh(
    locator: opts.Locator,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    common.main_callback(solution_path, log_level, version)

    model_ = factory.get_model()

    wrapper, diff = source.compare_entity_with_source(locator, model=model_)

    if not diff:
        typer.echo(f"No changes detected for '{locator}'")
        raise typer.Exit(0)

    typer.echo(
        f"Detected changes from sources: {[src.sourceLocation for src in wrapper.entity.sources]}"
    )

    # visualize the diff in a custom format, because the DeepDiffs COLOZRED_[COMPACT_]VIEW contain a
    # bug that messes up the visual diff

    if "values_changed" in diff:
        typer.echo("\nChanged Values")
        for path, change in diff["values_changed"].items():
            typer.echo(f" - {path}: ", nl=False)
            rich.print(f"{change['old_value']} -> {change['new_value']}")

    change_types = ("attribute", "iterable_item", "dictionary_item")
    change_operations = ("added", "removed")
    plain_entity = wrapper.entity.model_dump(mode="json")

    def print_change(key: str, diff, t, co):
        typer.echo(f"\n{co.capitalize()} {t}")
        for _, path in enumerate(diff[key]):
            typer.echo(f" - {path}: ", nl=False)
            rich.print(deepdiff.extract(plain_entity, path))

    for t in change_types:
        for co in change_operations:
            key = f"{t}_{co}"
            if key in diff:
                print_change(key, diff, t, co)

    ok = typer.prompt(
        "Should these changes be imported [yN]",
        default="n",
        show_choices=False,
        show_default=False,
        type=Choice(choices=["y", "Y", "n", "N"]),
        value_proc=lambda val: val.lower() == "y",
    )

    if not ok:
        raise typer.Exit(1)

    model_.modelEntities[wrapper.locator].update(**wrapper.entity.model_dump())
    model_.save()

    typer.echo("Saved detected changes")


@app.command()
def metadata(
    data_source_name: opts.DataSource,
    source_location: opts.SourceLocation,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Retrieve metadata from a source object"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    metadata = plugin.get_table_metadata(source_location)
    metadata.dataframe.show(
        limit=None,
        tbl_hide_dataframe_shape=True,
        tbl_cols=8,
    )


@app.command()
def test_connection(
    data_source_name: opts.DataSource,
    solution_path: opts.SolutionPath,
    log_level: opts.LogLevel = opts.LogLevels.WARNING,
    version: opts.Version = False,
):
    "Validate connectionstring and try connecting to the source"
    common.main_callback(solution_path, log_level, version)

    plugin = factory.get_plugin_for_data_source(data_source_name)
    plugin.test_connection()

    typer.echo("Datasource tested successfully")
