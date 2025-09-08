from typing import Annotated
import typer

app = typer.Typer()


@app.command("reverse")
def command(
    data_source: Annotated[
        str | None,
        typer.Option(
            "--data-source",
            help="Name of the data source for reverse generation (required for reverse_generate).",
        ),
    ] = None,
    data_product: Annotated[
        str | None,
        typer.Option(
            "--data-product",
            help="Data product name for output path (required for reverse_generate).",
        ),
    ] = None,
    data_module: Annotated[
        str | None,
        typer.Option(
            "--data-module",
            help="Data module name for output path (required for reverse_generate).",
        ),
    ] = None,
    tables: Annotated[
        str | None,
        typer.Option(
            "--tables",
            help="Comma-separated list of table names to reverse generate (required for reverse_generate).",
        ),
    ] = None,
    entity_names: Annotated[
        str | None,
        typer.Option(
            "--entity-names",
            help="Comma-separated list of entity names corresponding to tables (optional for reverse_generate).",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            help="Enable interactive mode for reverse generation with user prompts.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Set log level: NOTSET, DEBUG, INFO, WARN, ERROR, CRITICAL (default INFO).",
        ),
    ] = "INFO",
):
    """Generate a datam8 model file from a source object."""
    ...
