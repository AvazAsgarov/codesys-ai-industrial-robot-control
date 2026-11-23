"""Cell configuration loading and validation.

The single source of configuration is ``config/cell.yaml`` at the repository root.
Every model is frozen and rejects unknown keys, so typos fail loudly at start-up.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the first directory that contains ``pyproject.toml``."""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    msg = f"pyproject.toml not found above {start}"
    raise RuntimeError(msg)


REPO_ROOT: Path = _find_repo_root(Path(__file__).resolve().parent)
DEFAULT_CONFIG_PATH: Path = REPO_ROOT / "config" / "cell.yaml"


class ConfigError(Exception):
    """Raised when the cell configuration is missing or invalid."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectInfo(_Frozen):
    """Project identity."""

    name: str
    version: str


class PlcInfo(_Frozen):
    """PLC project location and OPC UA endpoint."""

    project_file: Path
    opcua_endpoint: str


class CellConfig(_Frozen):
    """Root of the cell configuration."""

    project: ProjectInfo
    plc: PlcInfo


def _format_validation_error(err: ValidationError) -> str:
    lines = [
        f"  {'.'.join(str(part) for part in e['loc']) or '<root>'}: {e['msg']}"
        for e in err.errors()
    ]
    return "invalid configuration:\n" + "\n".join(lines)


def load_config(path: Path | None = None) -> CellConfig:
    """Load and validate the cell configuration.

    Args:
        path: YAML file to load. Defaults to ``config/cell.yaml`` in the repository root,
            independent of the current working directory.

    Returns:
        The validated, immutable configuration.

    Raises:
        ConfigError: If the file is missing, is not valid YAML, or fails validation.
    """
    config_path = path if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        msg = f"configuration file not found: {config_path}"
        raise ConfigError(msg)
    try:
        raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"configuration file is not valid YAML: {config_path}: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"configuration file must contain a mapping at the top level: {config_path}"
        raise ConfigError(msg)
    try:
        return CellConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc
