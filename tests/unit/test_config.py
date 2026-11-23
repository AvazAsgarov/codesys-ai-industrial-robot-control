from pathlib import Path

import pydantic
import pytest

from airc.common.config import ConfigError, load_config
from tests.conftest import VALID_YAML


def test_load_config_default():
    cfg = load_config()
    assert cfg.project.name == "codesys-ai-industrial-robot-control"
    assert cfg.plc.opcua_endpoint == "opc.tcp://localhost:4840"


def test_load_config_default_path_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.plc.project_file == Path("plc/RobotCell.project")


def test_load_config_unknown_key_rejected(write_yaml):
    bad = VALID_YAML.replace("opcua_endpoint:", "opcua_endpointt:")
    with pytest.raises(ConfigError, match="opcua_endpointt"):
        load_config(write_yaml(bad))


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_load_config_empty_file(write_yaml):
    with pytest.raises(ConfigError):
        load_config(write_yaml(""))


def test_config_is_frozen():
    cfg = load_config()
    with pytest.raises(pydantic.ValidationError):
        cfg.project.name = "x"  # type: ignore[misc]
