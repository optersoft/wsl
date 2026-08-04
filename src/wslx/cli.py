"""`wslx` — Ubuntu WSL virtual machine manager."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, wsl
from .wsl import WslError

app = typer.Typer(
    name="wslx",
    help="Manage Ubuntu WSL virtual machines.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
errors = Console(stderr=True)

NameArg = Annotated[str, typer.Argument(help="Distribution name.")]
NamesArg = Annotated[list[str], typer.Argument(help="Distribution names.")]


def _version(value: bool) -> None:
    if value:
        console.print(f"wslx {__version__}")
        raise typer.Exit


@app.callback()
def main_callback(
    version: Annotated[  # noqa: ARG001 - consumed by the eager callback
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    pass


@app.command()
def create(names: NamesArg) -> None:
    """Create one or more WSL distributions."""
    for name in names:
        wsl.create(name)


@app.command()
def start(names: NamesArg) -> None:
    """Start one or more WSL distributions."""
    for name in names:
        wsl.start(name)


@app.command()
def stop(names: NamesArg) -> None:
    """Stop (terminate) one or more WSL distributions."""
    for name in names:
        wsl.stop(name)


@app.command()
def delete(names: NamesArg) -> None:
    """Delete one or more WSL distributions."""
    for name in names:
        wsl.delete(name)


@app.command(name="list")
def list_() -> None:
    """List WSL distributions."""
    distributions = wsl.list_distributions()
    if not distributions:
        console.print("No WSL distributions registered.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Version")
    table.add_column("Managed")

    for distribution in distributions:
        name = f"{distribution.name} *" if distribution.default else distribution.name
        managed = "yes" if wsl.managed(distribution.name) else "no"
        table.add_row(name, distribution.state, distribution.version, managed)

    console.print(table)
    console.print("[dim]* default distribution[/dim]")


@app.command()
def connect(
    name: NameArg,
    new: Annotated[
        bool,
        typer.Option("--new", "-n", help="Create the distribution first."),
    ] = False,
) -> None:
    """Open a shell in a WSL distribution."""
    wsl.connect(name, new)


def main() -> None:
    """Console-script entry point: turn `WslError` into a tidy exit."""
    try:
        app()
    except WslError as err:
        errors.print(f"[red]error:[/red] {err}")
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
