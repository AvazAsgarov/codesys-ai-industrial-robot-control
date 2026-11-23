"""Command-line interface: ``airc``."""

from pathlib import Path
from typing import Annotated

import typer
import yaml

from airc import __version__
from airc.common.config import ConfigError, load_config

app = typer.Typer(
    name="airc",
    help="AI Industrial Robot Control: services for the robotic sorting cell.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
config_app = typer.Typer(help="Inspect the cell configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")

EXIT_CONFIG_ERROR = 2


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"airc {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[  # noqa: ARG001 - consumed by the eager callback
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """AI Industrial Robot Control."""


@config_app.command("show")
def config_show(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to a cell.yaml (default: config/cell.yaml)."),
    ] = None,
) -> None:
    """Validate the configuration and print it as YAML."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None
    typer.echo(yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False).rstrip())
