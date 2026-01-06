"""Main CLI entrypoint for mm-cli."""

import typer

app = typer.Typer(
    name="mm",
    help="CLI tool for MoneyMoney macOS app - manage accounts, transactions and categories via AppleScript",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show version information."""
    from mm_cli import __version__

    typer.echo(f"mm-cli version {__version__}")


if __name__ == "__main__":
    app()
