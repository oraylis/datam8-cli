from typing import Annotated, Optional
import typer

app = typer.Typer()


@app.command("reverse")
def command(
    data_source: Annotated[
        Optional[str],
        typer.Option(
            "--data-source",
            help="Name of the data source for reverse generation (required for reverse_generate).",
        ),
    ] = None,
    data_product: Annotated[
        Optional[str],
        typer.Option(
            "--data-product",
            help="Data product name for output path (required for reverse_generate).",
        ),
    ] = None,
    data_module: Annotated[
        Optional[str],
        typer.Option(
            "--data-module",
            help="Data module name for output path (required for reverse_generate).",
        ),
    ] = None,
    tables: Annotated[
        Optional[str],
        typer.Option(
            "--tables",
            help="Comma-separated list of table names to reverse generate (required for reverse_generate).",
        ),
    ] = None,
    entity_names: Annotated[
        Optional[str],
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
): ...
