from pathlib import Path

from typer.testing import CliRunner

import airc
from airc.cli import _decision_config, _decision_worker, app
from airc.common.config import load_config
from airc.twin.scenario import Scenario
from tests.conftest import VALID_YAML

DEMO = Path(__file__).resolve().parents[2] / "config" / "scenarios" / "p2_demo.yaml"

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"airc {airc.__version__}" in result.output


def test_cli_config_show():
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "opc.tcp://127.0.0.1:4840" in result.output


def test_cli_bad_config_exit_code(write_yaml):
    bad = write_yaml(VALID_YAML.replace("opcua_endpoint:", "opcua_endpointt:"))
    result = runner.invoke(app, ["config", "show", "--config", str(bad)])
    assert result.exit_code == 2
    assert "opcua_endpointt" in result.output
    assert "Traceback" not in result.output


def test_cli_run_rejects_an_unknown_decision_mode():
    result = runner.invoke(app, ["run", "--decision", "thx99"])
    assert result.exit_code == 2
    assert "--decision thx02|replay:<path>|off" in result.output


def test_cli_run_decision_needs_vision():
    result = runner.invoke(app, ["run", "--decision", "thx02", "--vision", "oracle"])
    assert result.exit_code == 2
    assert "needs --vision yoloe" in result.output


def test_cli_run_missing_replay_file(tmp_path):
    missing = tmp_path / "none.jsonl"
    result = runner.invoke(app, ["run", "--decision", f"replay:{missing}", "--vision", "yoloe"])
    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_decision_config_choices(tmp_path):
    base = load_config().decision
    assert _decision_config(base, "off") is None
    api = _decision_config(base, "thx02")
    assert api is not None
    assert api.mode == "api"
    assert api.base_url == base.base_url
    rec = tmp_path / "run.jsonl"
    replay = _decision_config(base, f"replay:{rec}")
    assert replay is not None
    assert (replay.mode, replay.replay_file) == ("replay", rec)


def test_decision_worker_never_prints_the_api_key(monkeypatch, capsys):
    cfg = load_config().decision
    monkeypatch.setenv(cfg.api_key_env, "sk-secret-123")
    api = _decision_config(cfg, "thx02")
    assert api is not None
    worker = _decision_worker(api.model_copy(update={"record_dir": None}), Scenario.load(DEMO))
    worker.close()
    out = capsys.readouterr().out
    assert "set" in out
    assert "sk-secret-123" not in out
