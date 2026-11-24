from pathlib import Path

import pydantic
import pytest

from airc.common.config import CONFIG_ENV_VAR, ConfigError, default_config_path, load_config
from tests.conftest import VALID_YAML

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_config_default():
    cfg = load_config()
    assert cfg.project.name == "codesys-ai-industrial-robot-control"
    assert cfg.plc.opcua_endpoint == "opc.tcp://127.0.0.1:4840"


def test_load_config_default_path_independent_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.project.name == "codesys-ai-industrial-robot-control"


def test_relative_paths_resolve_against_repo_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.plc.project_file == REPO_ROOT / "plc" / "RobotCell.project"
    assert cfg.plc.project_file.is_file()


def test_relative_paths_in_custom_file_resolve_against_its_folder(write_yaml, tmp_path: Path):
    cfg = load_config(write_yaml(VALID_YAML))
    assert cfg.plc.project_file == tmp_path / "plc" / "RobotCell.project"


def test_env_var_overrides_default_path(write_yaml, monkeypatch: pytest.MonkeyPatch):
    custom = write_yaml(VALID_YAML.replace("version: 0.1.0", "version: 9.9.9"))
    monkeypatch.setenv(CONFIG_ENV_VAR, str(custom))
    assert default_config_path() == custom
    assert load_config().project.version == "9.9.9"


def test_default_config_path_not_found_raises_config_error(tmp_path: Path):
    with pytest.raises(ConfigError, match=r"cell\.yaml"):
        default_config_path(search_from=[tmp_path])


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


def test_decision_block_of_the_shipped_config():
    dec = load_config().decision
    assert dec.mode == "api"
    assert dec.base_url == "https://api.hal-x.ai"
    assert dec.model == "thx-02"
    assert dec.deadline_s == 2.5
    assert dec.rate_limit_per_min <= 60
    assert dec.record_dir == REPO_ROOT / "experiments" / "recordings" / "thx02"


def test_decision_defaults_to_off_when_absent(write_yaml):
    assert load_config(write_yaml(VALID_YAML)).decision.mode == "off"


def test_decision_replay_needs_a_file(write_yaml):
    with pytest.raises(ConfigError, match="replay_file"):
        load_config(write_yaml(VALID_YAML + "decision:\n  mode: replay\n"))


def test_decision_api_needs_a_base_url(write_yaml):
    with pytest.raises(ConfigError, match="base_url"):
        load_config(write_yaml(VALID_YAML + "decision:\n  mode: api\n"))


def test_decision_rate_limit_above_free_tier_rejected(write_yaml):
    text = VALID_YAML + "decision:\n  mode: off\n  rate_limit_per_min: 61\n"
    with pytest.raises(ConfigError, match="rate_limit_per_min"):
        load_config(write_yaml(text))


def test_decision_replay_file_resolves_against_config_folder(write_yaml, tmp_path: Path):
    text = VALID_YAML + "decision:\n  mode: replay\n  replay_file: rec/run.jsonl\n"
    assert load_config(write_yaml(text)).decision.replay_file == tmp_path / "rec" / "run.jsonl"
