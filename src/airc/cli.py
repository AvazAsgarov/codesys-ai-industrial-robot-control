"""Command-line interface: ``airc``."""

from pathlib import Path
from typing import Annotated

import typer
import yaml

from airc import __version__
from airc.common.config import ConfigError, load_config
from airc.plc import runtime
from airc.plc.runtime import RuntimeSettings, load_runtime_settings

app = typer.Typer(
    name="airc",
    help="AI Industrial Robot Control: services for the robotic sorting cell.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
config_app = typer.Typer(help="Inspect the cell configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")
plc_app = typer.Typer(
    help="Run and deploy the soft-PLC (CODESYS Control Win).", no_args_is_help=True
)
app.add_typer(plc_app, name="plc")

EXIT_CONFIG_ERROR = 2
EXIT_PLC_ERROR = 3


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"airc {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
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
    # The types-PyYAML stubs leave one safe_dump parameter partially unknown.
    dumped: str = yaml.safe_dump(  # pyright: ignore[reportUnknownMemberType]
        cfg.model_dump(mode="json"), sort_keys=False
    )
    typer.echo(dumped.rstrip())


def _runtime_settings() -> RuntimeSettings:
    try:
        return load_runtime_settings()
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None


@plc_app.command("start")
def plc_start() -> None:
    """Start the soft-PLC as a console process (applies config/runtime.yaml first)."""
    settings = _runtime_settings()
    try:
        pid = runtime.start(settings)
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_PLC_ERROR) from None
    typer.echo(f"soft-PLC running (pid {pid})")
    if runtime.firewall_allows_inbound(settings.executable):
        typer.echo(
            "warning: a Windows firewall rule lets the network reach the soft-PLC while anonymous "
            'login is allowed; run (admin): Disable-NetFirewallRule -DisplayName "CODESYS Control '
            'Service" (ADR 0008)',
            err=True,
        )


@plc_app.command("stop")
def plc_stop() -> None:
    """Stop the soft-PLC started by `airc plc start`."""
    typer.echo("soft-PLC stopped" if runtime.stop() else "soft-PLC was not running")


@plc_app.command("status")
def plc_status() -> None:
    """Show whether the soft-PLC process and its ports are up."""
    st = runtime.status(_runtime_settings())
    typer.echo(f"pid: {st.pid}  alive: {st.process_alive}")
    typer.echo(f"programming port open: {st.programming_port_open}")
    typer.echo(f"OPC UA port open: {st.opcua_port_open}")
    typer.echo(f"PackML state (GVL_Bridge.eState): {st.packml_state}")


@plc_app.command("deploy")
def plc_deploy(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to a cell.yaml (default: config/cell.yaml)."),
    ] = None,
) -> None:
    """Download the PLC application to the running soft-PLC and start it (takes minutes)."""
    try:
        cfg = load_config(config)
        log = runtime.deploy(_runtime_settings(), cfg.plc.project_file)
    except (ConfigError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_PLC_ERROR) from None
    typer.echo(log.rstrip())
