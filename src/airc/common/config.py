"""Cell configuration loading and validation.

The single source of configuration is ``config/cell.yaml`` at the repository root.
Every model is frozen and rejects unknown keys, so typos fail loudly at start-up.

Relative paths inside a configuration file are resolved against its *base directory*:
the folder that contains the ``config/`` folder (the repository root for ``config/cell.yaml``),
or the file's own folder when it does not live in a ``config/`` folder.
"""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Self, cast

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

CONFIG_ENV_VAR = "AIRC_CONFIG"
_CONFIG_RELATIVE = Path("config") / "cell.yaml"


class ConfigError(Exception):
    """Raised when the cell configuration is missing or invalid."""


def default_config_path(search_from: Sequence[Path] | None = None) -> Path:
    """Locate the cell configuration file.

    Order: the ``AIRC_CONFIG`` environment variable, then the first ``config/cell.yaml`` found
    walking up from each start directory (default: this module's folder, then the CWD).

    Args:
        search_from: Directories to start the upward search from.

    Returns:
        Path to the configuration file.

    Raises:
        ConfigError: If no configuration file can be located.
    """
    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        return Path(env_value)
    starts = (
        list(search_from)
        if search_from is not None
        else [Path(__file__).resolve().parent, Path.cwd()]
    )
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / _CONFIG_RELATIVE).is_file():
                return candidate / _CONFIG_RELATIVE
    msg = f"could not locate {_CONFIG_RELATIVE.as_posix()}; pass --config or set {CONFIG_ENV_VAR}"
    raise ConfigError(msg)


def _base_dir(config_path: Path) -> Path:
    folder = config_path.resolve().parent
    return folder.parent if folder.name == "config" else folder


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectInfo(_Frozen):
    """Project identity."""

    name: str
    version: str


def _resolve(value: Path | None, info: ValidationInfo) -> Path | None:
    context = cast("dict[str, Any] | None", info.context)
    base = context.get("base_dir") if context else None
    if value is None or value.is_absolute() or not isinstance(base, Path):
        return value
    return base / value


class PlcInfo(_Frozen):
    """PLC project location and OPC UA endpoint."""

    project_file: Path
    opcua_endpoint: str

    @field_validator("project_file")
    @classmethod
    def _resolve_relative(cls, value: Path, info: ValidationInfo) -> Path:
        return value if (resolved := _resolve(value, info)) is None else resolved


class DecisionConfig(_Frozen):
    """THX-02 decision layer (spec 7, ADR 0006). Absent from the file: ``mode: off``."""

    mode: Literal["api", "replay", "off"] = "off"
    base_url: str = ""  # API root; required for mode api
    model: str = "thx-02"
    deadline_s: float = Field(default=2.5, gt=0)  # recipe default; timeout -> fallback
    request_timeout_s: float = Field(default=2.0, gt=0)  # per HTTP call
    # The free tier allows 60 decisions per minute per IP and counts every question, so one
    # part (two questions) costs two tokens: 50 per minute = 25 parts per minute.
    rate_limit_per_min: float = Field(default=50.0, gt=0, le=60)
    burst: float = Field(default=2.0, ge=2)  # >= the decisions of one part
    max_retry_wait_s: float = Field(default=1.0, ge=0)  # longer Retry-After -> fallback
    max_429_retries: int = Field(default=1, ge=0)
    unreliable_no_prob: float = Field(default=0.8, gt=0, le=1)  # P(no) -> unreliable
    api_key_env: str = "HALX_API_KEY"  # optional key; the free tier needs none
    record_dir: Path | None = None  # JSONL per run; None = do not record
    replay_file: Path | None = None  # recording to answer from in mode replay

    @field_validator("record_dir", "replay_file")
    @classmethod
    def _resolve_relative(cls, value: Path | None, info: ValidationInfo) -> Path | None:
        return _resolve(value, info)

    @model_validator(mode="after")
    def _mode_needs(self) -> Self:
        if self.mode == "api" and not self.base_url:
            msg = "base_url is required for mode api"
            raise ValueError(msg)
        if self.mode == "replay" and self.replay_file is None:
            msg = "replay_file is required for mode replay"
            raise ValueError(msg)
        return self


class CellConfig(_Frozen):
    """Root of the cell configuration."""

    project: ProjectInfo
    plc: PlcInfo
    decision: DecisionConfig = DecisionConfig()


def _format_validation_error(err: ValidationError) -> str:
    lines = [
        f"  {'.'.join(str(part) for part in e['loc']) or '<root>'}: {e['msg']}"
        for e in err.errors()
    ]
    return "invalid configuration:\n" + "\n".join(lines)


def load_config(path: Path | None = None) -> CellConfig:
    """Load and validate the cell configuration.

    Args:
        path: YAML file to load. Defaults to :func:`default_config_path`.

    Returns:
        The validated, immutable configuration, with relative paths made absolute.

    Raises:
        ConfigError: If the file is missing, is not valid YAML, or fails validation.
    """
    config_path = path if path is not None else default_config_path()
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
        return CellConfig.model_validate(raw, context={"base_dir": _base_dir(config_path)})
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc
