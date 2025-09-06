import typer

from .cmd import generate, reverse, validate

app = typer.Typer(
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=True,
    pretty_exceptions_short=False,
)

app.add_typer(generate.app)
app.add_typer(validate.app)
app.add_typer(reverse.app)

if __name__ == "__main__":
    app()
