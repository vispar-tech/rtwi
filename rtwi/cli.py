from __future__ import annotations

import typer
from rich.console import Console

from rtwi import __version__

app = typer.Typer(
    help="Automatic Rostelecom commercial Wi-Fi authorization + MAC roll",
    no_args_is_help=True,
    invoke_without_command=True,
    rich_markup_mode="rich",
)
console = Console()


@app.callback()
def cli_main(
    _ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Root CLI entry point; handles --version."""
    if version:
        console.print(f"rtwi {__version__}")
        raise typer.Exit


if __name__ == "__main__":
    app()
